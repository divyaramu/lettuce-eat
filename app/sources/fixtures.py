"""Offline provider for tests/demos: deterministic Seattle-style fixtures from tests/fixtures/venues.json."""
import json
from pathlib import Path

from ..models import SourceKind, Venue
from .base import Page

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "venues.json"


class FixtureProvider:
    def __init__(self, path: Path = FIXTURE):
        self._data = json.loads(path.read_text())

    def find_venues(self, area, limit, lat=None, lon=None, radius_km=None):
        return [Venue(**v["venue"]) for v in self._data][:limit]

    def pages_for(self, venue):
        for v in self._data:
            if v["venue"]["name"] == venue.name:
                return [Page(url=p["url"], text=p["text"], kind=SourceKind(p["kind"])) for p in v["pages"]]
        return []
