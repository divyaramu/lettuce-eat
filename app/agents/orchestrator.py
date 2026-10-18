"""Pipeline: venues -> pages (per source) -> extract -> verify -> tier per restriction -> group-safe ranking.
Per-venue work runs in a thread pool; one failing venue never fails the report."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from ..models import Group, GroupReport, Restriction, Venue, VenueReport
from ..sources.base import SourceProvider
from .extractor import Extractor
from .scoring import tier_for, venue_score


def group_restrictions(group: Group) -> list[Restriction]:
    seen: dict[Restriction, None] = {}
    for m in group.members:
        for r in m.restrictions:
            if isinstance(r, Restriction):
                seen[r] = None
                continue
            key = str(r).strip().lower().replace(" ", "_")
            try:
                seen[Restriction(key)] = None
            except ValueError:
                pass
    return list(seen)


def analyze_venue(venue: Venue, restrictions: list[Restriction], provider: SourceProvider,
                  extractor: Extractor) -> VenueReport:
    evidence = []
    for page in provider.pages_for(venue):
        evidence += extractor.extract(page.text, page.url, page.kind, restrictions, venue.name)
    results = [tier_for(r, evidence) for r in restrictions]
    score = venue_score(results)
    weak = [r.restriction.value.replace("_", " ") for r in results if r.tier.value in ("questionable", "reported_unsafe")]
    summary = ("Every member has a sourced option." if not weak and results else
               f"Needs a call or has warnings for: {', '.join(weak)}." if weak else "No restrictions to check.")
    return VenueReport(venue=venue, results=results, score=score, summary=summary)


def build_report(group: Group, provider: SourceProvider, extractor: Extractor, limit: int = 6) -> GroupReport:
    restrictions = group_restrictions(group)
    venues = provider.find_venues(group.area, limit, getattr(group, "lat", None), getattr(group, "lon", None),
                                getattr(group, "radius_km", None))

    def one(v: Venue) -> VenueReport | None:
        try:
            return analyze_venue(v, restrictions, provider, extractor)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        reports = [r for r in ex.map(one, venues) if r]
    reports.sort(key=lambda r: r.score, reverse=True)
    return GroupReport(group_id=group.id, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       venues=reports)
