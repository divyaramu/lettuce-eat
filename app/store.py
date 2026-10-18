"""In-memory store (hackathon). Swap for SQLite/Postgres later. Thread-safe."""
import threading

from .models import Group, GroupReport, Member, Restriction
from .security import clean_text, new_token


class Store:
    def __init__(self, max_members: int = 12):
        self._lock = threading.Lock()
        self._groups: dict[str, Group] = {}
        self._reports: dict[str, GroupReport] = {}
        self.max_members = max_members

    def create_group(self, area: str = "Seattle, WA", lat: float | None = None, lon: float | None = None,
                    radius_km: float = 2.0) -> Group:
        g = Group(id=new_token(8), join_token=new_token(16), area=clean_text(area, 80) or "Seattle, WA",
                  lat=lat, lon=lon, radius_km=radius_km)
        with self._lock:
            self._groups[g.id] = g
        return g

    def get(self, gid: str) -> Group | None:
        return self._groups.get(gid)

    def join(self, gid: str, token: str, nickname: str, restrictions: list[Restriction]) -> Member | None:
        with self._lock:
            g = self._groups.get(gid)
            if not g or not secrets_equal(g.join_token, token) or len(g.members) >= self.max_members:
                return None
            m = Member(id=new_token(6), nickname=nickname, restrictions=list(dict.fromkeys(restrictions)))
            g.members.append(m)
            return m

    def save_report(self, r: GroupReport) -> None:
        with self._lock:
            self._reports[r.group_id] = r

    def report(self, gid: str) -> GroupReport | None:
        return self._reports.get(gid)


def secrets_equal(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a.encode(), b.encode())
