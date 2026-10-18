from ..models import Evidence, Restriction, RestrictionResult, SourceKind, Tier

TIER_POINTS = {Tier.OFFICIAL: 1.0, Tier.COMMUNITY: 0.6, Tier.QUESTIONABLE: 0.15, Tier.UNSAFE: 0.0}


def tier_for(restriction: Restriction, evidence: list[Evidence]) -> RestrictionResult:
    mine = [e for e in evidence if e.restriction == restriction]
    official = [e for e in mine if e.source_kind == SourceKind.OFFICIAL]
    community = [e for e in mine if e.source_kind != SourceKind.OFFICIAL]
    official_warn = [e for e in official if e.stance == "warns"]
    official_ok = [e for e in official if e.stance == "supports"]
    community_ok = [e for e in community if e.stance == "supports"]
    community_warn = [e for e in community if e.stance == "warns"]

    if official_warn and not official_ok:
        return RestrictionResult(restriction=restriction, tier=Tier.UNSAFE, evidence=mine,
                                 note="Official source warns of cross-contact or lack of safe options.")
    if official_ok:
        note = "Official source states support."
        if official_warn or community_warn:
            note += " Note: a warning (e.g. cross-contact) also appears; confirm with the restaurant."
        return RestrictionResult(restriction=restriction, tier=Tier.OFFICIAL, evidence=mine, note=note)
    if community_ok and len(community_warn) < len(community_ok):
        return RestrictionResult(restriction=restriction, tier=Tier.COMMUNITY, evidence=mine,
                                 note="Community verified (not confirmed by the restaurant). Call to confirm.")
    if community_warn:
        return RestrictionResult(restriction=restriction, tier=Tier.UNSAFE, evidence=mine,
                                 note="Community reports problems.")
    return RestrictionResult(restriction=restriction, tier=Tier.QUESTIONABLE, evidence=[],
                             note="Could not verify online. Call the restaurant to check.")


def venue_score(results: list[RestrictionResult]) -> float:
    """A venue is disqualified by an unsafe warning, but a single uncertain restriction should not tank the whole venue."""
    if not results:
        return 0.0
    if any(r.tier == Tier.UNSAFE for r in results):
        return 0.0
    return round(sum(TIER_POINTS[r.tier] for r in results) / len(results), 3)
