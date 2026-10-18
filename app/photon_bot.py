"""iMessage agent via Photon 2.0 (Beta) shared line.

Privacy model (like GamePigeon, not a chat reader):
 - The bot only ever sees DIRECT messages people choose to send to it. A shared line cannot join group chats.
 - Group coordination = the organizer texts the bot, gets a join link/code, and forwards it to the group chat themselves.
 - Nothing is stored except the restrictions a person explicitly submits. No message history is persisted.
Docs: https://photon.codes/docs/beta/get-started/imessage
"""
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Protocol

from .models import Restriction as R
from .store import Store

ALIASES: dict[R, list[str]] = {
    R.PEANUT_FREE: ["peanut"], R.TREE_NUT_FREE: ["tree nut", "almond", "cashew", "walnut"],
    R.SHELLFISH_FREE: ["shellfish", "shrimp", "crab"], R.DAIRY_FREE: ["dairy", "lactose"],
    R.EGG_FREE: ["egg"], R.SOY_FREE: ["soy"], R.SESAME_FREE: ["sesame"],
    R.GLUTEN_FREE: ["gluten", "celiac", "coeliac"], R.VEGAN: ["vegan"],
    R.VEGETARIAN: ["vegetarian"], R.HALAL: ["halal"], R.KOSHER: ["kosher"],
}
HELP = ("Lettuce Eat: find places where everyone can eat.\n"
        "• new – start a group\n• join <code> <nickname> <restrictions> – e.g. join abc.xyz Sam vegan, nut allergy\n"
        "• report <code> – results link\nI only read messages sent directly to me.")


def parse_restrictions(text: str) -> list[R]:
    t = text.lower()
    found = [r for r, words in ALIASES.items() if any(w in t for w in words)]
    if "nut" in t and not any(r in found for r in (R.PEANUT_FREE, R.TREE_NUT_FREE)):
        found += [R.PEANUT_FREE, R.TREE_NUT_FREE]  # bare "nut allergy" => be conservative: both
    return list(dict.fromkeys(found))


@dataclass
class Incoming:
    id: str
    space_id: str
    agent_id: str
    sender_handle: str
    text: str


class Transport(Protocol):
    def fetch_new(self) -> list[Incoming]: ...
    def reply(self, msg: Incoming, text: str) -> None: ...


class BotLogic:
    def __init__(self, store: Store, base_url: str, run_report: Callable[[str], None] | None = None,
                 per_min: int = 10):
        self.store, self.base, self.run_report = store, base_url, run_report
        self._hits: dict[str, deque] = defaultdict(deque)
        self.per_min = per_min

    def _limited(self, who: str, now: float) -> bool:
        q = self._hits[who]
        while q and now - q[0] > 60:
            q.popleft()
        q.append(now)
        return len(q) > self.per_min

    def handle(self, sender: str, text: str, now: float | None = None) -> str:
        now = time.monotonic() if now is None else now
        if self._limited(sender, now):
            return "Slow down a little and try again in a minute."
        text = (text or "").strip()[:500]
        cmd, _, rest = text.partition(" ")
        cmd = cmd.lower()
        if cmd == "new":
            g = self.store.create_group()
            return (f"Group created. Share this link with your group chat so everyone adds their needs:\n"
                    f"{self.base}/g/{g.id}?t={g.join_token}\n\nOr they can text me: join {g.id}.{g.join_token} <name> <restrictions>")
        if cmd == "join":
            m = re.match(r"([\w-]+)\.([\w-]+)\s+(\S+)\s*(.*)", rest)
            if not m:
                return "Format: join <code> <nickname> <restrictions>"
            gid, tok, nick, restr = m.groups()
            member = self.store.join(gid, tok, nick, parse_restrictions(restr))
            if not member:
                return "That code isn't valid (or the group is full)."
            got = ", ".join(r.value.replace("_", " ") for r in member.restrictions) or "none"
            return f"Added {member.nickname}. Restrictions: {got}."
        if cmd == "report":
            m = re.match(r"([\w-]+)\.([\w-]+)", rest.strip())
            g = self.store.get(m.group(1)) if m else None
            if not g or g.join_token != m.group(2):
                return "That code isn't valid."
            if self.run_report:
                self.run_report(g.id)
            return f"Your results (with sources you can check): {self.base}/g/{g.id}?t={g.join_token}"
        return HELP


def run_once(transport: Transport, logic: BotLogic, seen: set[str]) -> int:
    """Process new inbound messages once. Idempotent via `seen` (and Photon idempotency keys)."""
    n = 0
    for msg in transport.fetch_new():
        if msg.id in seen:
            continue
        seen.add(msg.id)
        transport.reply(msg, logic.handle(msg.sender_handle, msg.text))
        n += 1
    return n


class PhotonSDKTransport:
    """Beta (2.0) API client: package `photonhq-api` (import photon_api). Polls received DMs."""

    def __init__(self, api_key: str, project_id: str, agent_handle: str, platform: str = "imessage"):
        from photon_api import Photon
        self._photon = Photon(headers={"Authorization": f"Bearer {api_key}"})
        self.project, self.agent, self.platform = project_id, agent_handle, platform
        self._started = time.time()

    def fetch_new(self) -> list[Incoming]:
        from datetime import datetime, timedelta, timezone
        from photon_api.generated.models import TextContent, UserSnapshot
        from photon_api.rpc_generated import ListMessagesInput
        since = (datetime.fromtimestamp(self._started, timezone.utc) - timedelta(seconds=5)) \
            .isoformat(timespec="milliseconds").replace("+00:00", "Z")
        query = {"createdSince": since, "direction": "received", "order": "asc", "pageSize": 100, "platform": self.platform}
        out: list[Incoming] = []
        while True:
            page = self._photon.projects.list_messages(
                ListMessagesInput.model_validate({"path": {"id": self.project}, "query": query}))
            for item in page.items:
                m = item.root.root
                if m.platform != self.platform or m.status != "received" or not isinstance(m.receivedBy, UserSnapshot):
                    continue
                sender, agent, space = m.sentBy.root, m.receivedBy.root, m.space.root
                if sender.kind != "human" or agent.kind != "agent" or agent.handle != self.agent:
                    continue
                if space.kind != "direct":            # never process group spaces
                    continue
                if not isinstance(m.content, TextContent) or m.content.format != "plain":
                    continue
                out.append(Incoming(m.id, space.id, agent.id, sender.handle, m.content.text))
            token = page.nextPageToken
            if not isinstance(token, str):
                return out
            query["pageToken"] = token

    def reply(self, msg: Incoming, text: str) -> None:
        from photon_api.generated.models import SendMessageRequest, SendTextContent
        from photon_api.rpc_generated import SendMessageHeader, SendMessageInput, SendMessagePath
        self._photon.projects.send_message(SendMessageInput(
            path=SendMessagePath(id=self.project),
            headers=SendMessageHeader.model_validate({"idempotency-key": f"lettuce-eat-reply:{msg.id}"}),
            body=SendMessageRequest(spaceId=msg.space_id, senderId=msg.agent_id, parentMessageId=msg.id,
                                    content=SendTextContent(type="text", format="plain", text=text[:1500]))))


def start_bot_thread(store: Store, settings, provider, extractor) -> bool:
    """Run the poller in a daemon thread sharing the API's Store. Returns False if Photon isn't configured."""
    import threading
    from .agents.orchestrator import build_report
    if not settings.photon_enabled:
        return False
    if not (settings.photon_api_key and settings.photon_project_id and settings.photon_agent_handle):
        return False

    def run_report(gid: str) -> None:
        g = store.get(gid)
        if g and g.members:
            store.save_report(build_report(g, provider, extractor, settings.max_venues))

    logic = BotLogic(store, settings.public_base_url, run_report)
    transport = PhotonSDKTransport(settings.photon_api_key, settings.photon_project_id, settings.photon_agent_handle)
    seen: set[str] = set()

    def loop() -> None:
        while True:
            try:
                run_once(transport, logic, seen)
            except Exception as e:  # keep alive; never log message content
                print("photon poll error:", type(e).__name__)
                time.sleep(10)
            time.sleep(2.5)  # docs: don't poll faster; back off on 429

    threading.Thread(target=loop, daemon=True, name="photon-bot").start()
    return True
