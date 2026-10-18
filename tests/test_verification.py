from app.agents.extractor import RuleExtractor, verify_all, verify_quote
from app.models import Evidence, Restriction as R, SourceKind


def test_hallucinated_quote_is_dropped():
    page = "We serve a gluten-free menu every day."
    fake = Evidence(restriction=R.GLUTEN_FREE, stance="supports", quote="100% certified celiac safe kitchen",
                    url="https://x.test", source_kind=SourceKind.OFFICIAL)
    real = Evidence(restriction=R.GLUTEN_FREE, stance="supports", quote="a gluten-free menu every day",
                    url="https://x.test", source_kind=SourceKind.OFFICIAL)
    assert verify_all([fake, real], page) == [real]


def test_quote_matching_ignores_case_and_whitespace():
    assert verify_quote("GLUTEN-free   menu", "Our gluten-free menu is large.")


def test_rule_extractor_flags_cross_contact_as_warning():
    text = "We offer vegan dishes. Our kitchen has cross-contact with peanuts, so we are not peanut-free."
    evs = RuleExtractor().extract(text, "https://x.test", SourceKind.OFFICIAL, [R.PEANUT_FREE, R.VEGAN])
    stances = {(e.restriction, e.stance) for e in evs}
    assert (R.PEANUT_FREE, "warns") in stances and (R.VEGAN, "supports") in stances
