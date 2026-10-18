from dataclasses import dataclass
from typing import Protocol

from ..models import SourceKind, Venue


@dataclass
class Page:
    url: str
    text: str
    kind: SourceKind


class SourceProvider(Protocol):
    def find_venues(self, area: str, limit: int, lat: float | None = None, lon: float | None = None,
                   radius_km: float | None = None) -> list[Venue]: ...
    def pages_for(self, venue: Venue) -> list[Page]: ...
