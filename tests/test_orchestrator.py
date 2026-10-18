from app.agents.extractor import RuleExtractor
from app.agents.orchestrator import build_report
from app.agents.scoring import venue_score
from app.models import Group, Member, Restriction as R, RestrictionResult, Tier
from app.sources.fixtures import FixtureProvider
from app.store import Store


def group(*members):
    return Group(id="g1", join_token="t", members=list(members))


def test_everyone_fed_venue_ranks_first_and_is_sourced():
    g = group(Member(id="1", nickname="A", restrictions=[R.GLUTEN_FREE, R.VEGAN]),
              Member(id="2", nickname="B", restrictions=[R.HALAL, R.PEANUT_FREE]))
    rep = build_report(g, FixtureProvider(), RuleExtractor())
    top = rep.venues[0]
    assert top.venue.name == "Cedar & Salt"
    assert all(r.tier == Tier.OFFICIAL for r in top.results)
    assert all(e.quote and e.url.startswith("https://") for r in top.results for e in r.evidence)


def test_unverifiable_venue_is_questionable_not_hidden():
    g = group(Member(id="1", nickname="A", restrictions=[R.HALAL]))
    rep = build_report(g, FixtureProvider(), RuleExtractor())
    mystery = next(v for v in rep.venues if v.venue.name == "Mystery Grill")
    assert mystery.results[0].tier == Tier.QUESTIONABLE and "call" in mystery.results[0].note.lower()


def test_official_warning_marks_unsafe_and_community_only_is_labelled():
    g = group(Member(id="1", nickname="A", restrictions=[R.PEANUT_FREE, R.VEGAN]))
    rep = build_report(g, FixtureProvider(), RuleExtractor())
    nh = next(v for v in rep.venues if v.venue.name == "Noodle Harbor")
    tiers = {r.restriction: r.tier for r in nh.results}
    assert tiers[R.PEANUT_FREE] == Tier.UNSAFE
    assert tiers[R.VEGAN] == Tier.COMMUNITY
    assert nh.score == 0.0  # weakest member decides


def test_venue_score_is_not_crushed_by_one_questionable_restriction():
    results = [
        RestrictionResult(restriction=R.GLUTEN_FREE, tier=Tier.OFFICIAL, evidence=[], note="official"),
        RestrictionResult(restriction=R.VEGAN, tier=Tier.QUESTIONABLE, evidence=[], note="unclear")
    ]
    assert venue_score(results) > 0.5


def test_group_store_keeps_geo_search_fields():
    g = Store().create_group(area="Seattle, WA", lat=47.6062, lon=-122.3321, radius_km=5)
    assert g.lat == 47.6062
    assert g.lon == -122.3321
    assert g.radius_km == 5
