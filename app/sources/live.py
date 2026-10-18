"""Live provider. Runs inside the Docker sandbox.
 - Venues: OpenStreetMap Overpass (free, no key). Website tag = official site.
 - Official pages: homepage + menu-ish links, fetched via SafeFetcher (SSRF-guarded).
 - Community: Reddit public search JSON + Gemini-grounded web search for blogs/reviews/social.
All fetched text is untrusted; only quotes re-verified against it become evidence."""
import re
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..models import SourceKind, Venue
from ..security import SafeFetcher, validate_public_url, UnsafeURL
from .base import Page

OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "LettuceEatBot/0.1 (hackathon)"}
MENU_HINT = re.compile(r"menu|allerg|dietary|nutrition|gluten|vegan|faq", re.I)
SOCIAL_HOSTS = ("instagram.com", "facebook.com", "tiktok.com", "x.com", "twitter.com")
BLOG_REVIEW_HOSTS = ("yelp.com", "tripadvisor.com", "eater.com", "seattlemet.com", "thestranger.com")

def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    return re.sub(r"\n{2,}", "\n", soup.get_text("\n"))


def osm_url_for(item: dict) -> str | None:
    item_type = item.get("type") or item.get("osm_type")
    item_id = item.get("id") or item.get("osm_id")
    if item_type and item_id:
        return f"https://www.openstreetmap.org/{item_type}/{item_id}"
    return None


class LiveProvider:
    def __init__(self, fetcher: SafeFetcher | None = None, grounded_search=None):
        self.fetch = fetcher or SafeFetcher()
        self.grounded_search = grounded_search  # callable(query)->list[str urls]; optional (Gemini grounding)
        self._http = httpx.Client(timeout=15, headers=UA)

    def _google_venues(self, area: str, limit: int, lat: float | None = None, lon: float | None = None,
                       radius_km: float | None = None) -> list[Venue]:
        if not self.grounded_search:
            return []

        query = f"restaurants in {area}"
        if lat is not None and lon is not None:
            query += f" near {lat},{lon}"
        if radius_km is not None:
            query += f" within {radius_km} km"
        query += " popular dining"

        seen: set[str] = set()
        venues: list[Venue] = []
        for url in self.grounded_search(query)[: max(limit * 5, 10)]:
            try:
                validate_public_url(url)
            except UnsafeURL:
                continue
            if url in seen:
                continue
            seen.add(url)
            page = self.fetch.get(url)
            if not page:
                continue
            fetched_url, html = page
            title = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            name = BeautifulSoup(html, "html.parser").title.get_text(" ", strip=True) if BeautifulSoup(html, "html.parser").title else None
            if not name and title:
                name = re.sub(r"\s+", " ", title.group(1)).strip()
            if not name:
                name = urlparse(fetched_url).netloc.replace("www.", "")
            venues.append(Venue(name=name[:100], website=fetched_url, address="", phone=None))
            if len(venues) >= limit:
                break
        return venues

    def find_venues(self, area: str, limit: int, lat: float | None = None, lon: float | None = None,
                    radius_km: float | None = None) -> list[Venue]:
        google_hits = self._google_venues(area, limit, lat, lon, radius_km)
        if google_hits:
            return google_hits[:limit]

        venues: list[Venue] = []

        if lat is not None and lon is not None and radius_km is not None:
            radius_m = max(int(float(radius_km) * 1000), 500)
            query = f"""
            [out:json][timeout:25];
            (
              node["amenity"~"restaurant|cafe|fast_food|food_court"](around:{radius_m},{lat},{lon});
              node["shop"~"bakery|coffee"](around:{radius_m},{lat},{lon});
              node["cuisine"~"."](around:{radius_m},{lat},{lon});
              way["amenity"~"restaurant|cafe|fast_food|food_court"](around:{radius_m},{lat},{lon});
              way["shop"~"bakery|coffee"](around:{radius_m},{lat},{lon});
              way["cuisine"~"."](around:{radius_m},{lat},{lon});
              relation["amenity"~"restaurant|cafe|fast_food|food_court"](around:{radius_m},{lat},{lon});
              relation["shop"~"bakery|coffee"](around:{radius_m},{lat},{lon});
              relation["cuisine"~"."](around:{radius_m},{lat},{lon});
            );
            out center 200;
            """
            try:
                payload = self._http.post(OVERPASS, data={"data": query}, timeout=30).json()
                for item in payload.get("elements", [])[:limit * 6]:
                    tags = item.get("tags", {})
                    name = tags.get("name") or tags.get("brand") or tags.get("operator")
                    if not name:
                        continue
                    website = (
                        tags.get("website") or tags.get("contact:website") or tags.get("brand:website")
                        or tags.get("url") or osm_url_for(item)
                    )
                    if not website:
                        continue
                    lat_val = item.get("lat") or item.get("center", {}).get("lat")
                    lon_val = item.get("lon") or item.get("center", {}).get("lon")
                    if lat_val is None or lon_val is None:
                        continue
                    address = ", ".join(filter(None, [
                        tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city"),
                        tags.get("addr:state")
                    ]))
                    venues.append(Venue(name=str(name)[:100], address=address, website=website, phone=None))
                    if len(venues) >= limit:
                        break
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                venues = []

        if not venues:
            try:
                places = self._http.get(
                    NOMINATIM,
                    params={"q": f"restaurant {area}", "format": "jsonv2", "limit": max(limit * 3, 10), "addressdetails": 1},
                    timeout=30,
                ).json()
                for item in places:
                    name = item.get("name") or item.get("display_name")
                    if not name:
                        continue
                    site = item.get("website") or item.get("extratags", {}).get("website") or item.get("url")
                    if not site:
                        site = osm_url_for(item)
                    if not site:
                        continue
                    addr = item.get("address")
                    address = " ".join(filter(None, [
                        addr.get("house_number") if isinstance(addr, dict) else None,
                        addr.get("road") if isinstance(addr, dict) else None,
                        addr.get("city") if isinstance(addr, dict) else None,
                    ])) if isinstance(addr, dict) else ""
                    venues.append(Venue(name=str(name)[:100], address=address, website=site, phone=None))
                    if len(venues) >= limit:
                        break
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                venues = []

        return venues[:limit]

    def pages_for(self, venue: Venue) -> list[Page]:
        pages: list[Page] = []
        if venue.website:
            home = self.fetch.get(venue.website)
            if home:
                url, html = home
                pages.append(Page(url, html_to_text(html), SourceKind.OFFICIAL))
                soup = BeautifulSoup(html, "html.parser")
                host = urlparse(url).hostname
                seen = {url}
                for a in soup.find_all("a", href=True)[:200]:
                    link = urljoin(url, a["href"])
                    if urlparse(link).hostname == host and link not in seen and MENU_HINT.search(link + a.get_text()):
                        seen.add(link)
                        sub = self.fetch.get(link)
                        if sub:
                            pages.append(Page(sub[0], html_to_text(sub[1]), SourceKind.OFFICIAL))
                        if len(seen) >= 4:
                            break
        pages += self._reddit(venue)
        pages += self._web_community(venue)
        return pages

    def _reddit(self, venue: Venue) -> list[Page]:
        try:
            r = self._http.get("https://www.reddit.com/search.json",
                               params={"q": f'"{venue.name}" Seattle', "limit": 5, "sort": "relevance"})
            posts = r.json()["data"]["children"]
        except (httpx.HTTPError, ValueError, KeyError):
            return []
        out = []
        for p in posts:
            d = p["data"]
            text = f"{d.get('title','')}\n{d.get('selftext','')}"
            if venue.name.lower() in text.lower():
                out.append(Page("https://www.reddit.com" + d.get("permalink", ""), text, SourceKind.REDDIT))
        return out

    def _web_community(self, venue: Venue) -> list[Page]:
        if not self.grounded_search:
            return []
        out = []
        for url in self.grounded_search(f"{venue.name} Seattle gluten free vegan halal kosher allergy reviews")[:5]:
            try:
                validate_public_url(url)
            except UnsafeURL:
                continue
            got = self.fetch.get(url)
            if not got:
                continue
            host = urlparse(got[0]).hostname or ""
            kind = (SourceKind.SOCIAL if host.endswith(SOCIAL_HOSTS) else
                    SourceKind.REVIEW if host.endswith(BLOG_REVIEW_HOSTS) else SourceKind.BLOG)
            out.append(Page(got[0], html_to_text(got[1]), kind))
        return out
