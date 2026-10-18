"""Safety primitives: SSRF-safe fetching, input sanitising, unguessable tokens."""
import ipaddress
import re
import secrets
import socket
from urllib.parse import urlparse

import httpx

ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml", "application/json")


class UnsafeURL(ValueError):
    pass


def new_token(nbytes: int = 16) -> str:
    return secrets.token_urlsafe(nbytes)


def _ip_is_public(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
                or a.is_reserved or a.is_unspecified)


def validate_public_url(url: str, resolver=socket.getaddrinfo) -> str:
    """Raise UnsafeURL unless url is https and every resolved IP is public."""
    p = urlparse(url)
    if p.scheme != "https":
        raise UnsafeURL("only https URLs are allowed")
    if not p.hostname or p.username or p.password:
        raise UnsafeURL("bad host or embedded credentials")
    if p.port not in (None, 443):
        raise UnsafeURL("non-standard port")
    try:
        infos = resolver(p.hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeURL("DNS failure") from e
    ips = {i[4][0] for i in infos}
    if not ips or not all(_ip_is_public(ip) for ip in ips):
        raise UnsafeURL("host resolves to a non-public address")
    return url


class SafeFetcher:
    """Fetch untrusted pages: https only, public IPs only, redirects re-validated,
    size/time capped, content-type allowlisted. Never raises on remote errors; returns None."""

    def __init__(self, timeout: float = 8.0, max_bytes: int = 1_500_000, max_redirects: int = 3,
                 resolver=socket.getaddrinfo, client: httpx.Client | None = None):
        self.timeout, self.max_bytes, self.max_redirects = timeout, max_bytes, max_redirects
        self.resolver = resolver
        self._client = client or httpx.Client(follow_redirects=False, timeout=timeout,
                                              headers={"User-Agent": "LettuceEatBot/0.1 (+hackathon)"})

    def get(self, url: str) -> tuple[str, str] | None:
        """Returns (final_url, text) or None."""
        try:
            for _ in range(self.max_redirects + 1):
                validate_public_url(url, self.resolver)
                with self._client.stream("GET", url) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            return None
                        url = str(httpx.URL(url).join(loc))
                        continue
                    if r.status_code != 200:
                        return None
                    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype not in ALLOWED_CONTENT_TYPES:
                        return None
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf += chunk
                        if len(buf) > self.max_bytes:
                            break
                    return url, bytes(buf[: self.max_bytes]).decode(r.encoding or "utf-8", "replace")
            return None
        except (UnsafeURL, httpx.HTTPError):
            return None


_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(s: str, max_len: int = 200) -> str:
    """Strip control chars, collapse whitespace, cap length (for user-supplied labels)."""
    return re.sub(r"\s+", " ", _CTRL.sub("", s or "")).strip()[:max_len]


def normalize(s: str) -> str:
    """Canonical form for quote verification (case/space/quote-insensitive)."""
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s).strip().lower()
