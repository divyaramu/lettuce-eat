"""Keyword rules per restriction. Used by the deterministic extractor (no LLM needed)
and to pre-filter text before it goes to the LLM."""
import re
from .models import Restriction as R

SUPPORT_TERMS: dict[R, list[str]] = {
    R.PEANUT_FREE: ["peanut-free", "peanut free", "no peanuts", "nut-free", "nut free"],
    R.TREE_NUT_FREE: ["tree nut-free", "tree-nut free", "nut-free", "nut free", "no tree nuts"],
    R.SHELLFISH_FREE: ["shellfish-free", "shellfish free", "no shellfish"],
    R.DAIRY_FREE: ["dairy-free", "dairy free", "no dairy", "lactose-free", "lactose free"],
    R.EGG_FREE: ["egg-free", "egg free", "no eggs"],
    R.SOY_FREE: ["soy-free", "soy free", "no soy"],
    R.SESAME_FREE: ["sesame-free", "sesame free", "no sesame"],
    R.GLUTEN_FREE: ["gluten-free", "gluten free", "gf menu", "celiac", "coeliac"],
    R.VEGAN: ["vegan", "plant-based", "plant based"],
    R.VEGETARIAN: ["vegetarian", "vegan", "meat-free", "meatless"],
    R.HALAL: ["halal", "zabihah", "zabiha"],
    R.KOSHER: ["kosher", "certified kosher"],
}

# Phrases that WARN regardless of restriction keyword (cross-contact etc.)
WARN_PATTERNS = [
    r"cross[- ]contact", r"cross[- ]contamination", r"shared (fryer|fryers|grill|kitchen|equipment|surface)",
    r"may contain", r"not (a )?(gluten|nut|allergen)[- ]free", r"not (suitable|safe)", r"processed in a facility",
    r"not halal", r"not kosher", r"contains (peanuts|tree nuts|shellfish|dairy|egg|soy|sesame|gluten)",
]
_WARN = re.compile("|".join(WARN_PATTERNS), re.I)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if 8 <= len(p.strip()) <= 400]


def sentence_mentions(sentence: str, restriction: R) -> bool:
    s = sentence.lower()
    return any(t in s for t in SUPPORT_TERMS[restriction])


def sentence_warns(sentence: str) -> bool:
    return bool(_WARN.search(sentence))


# Nouns that tie a WARNING sentence ("cross-contact with peanuts") to a restriction.
ALLERGEN_NOUNS: dict[R, list[str]] = {
    R.PEANUT_FREE: ["peanut"], R.TREE_NUT_FREE: ["tree nut", "almond", "cashew", "walnut", "pecan", "pistachio", " nuts"],
    R.SHELLFISH_FREE: ["shellfish", "shrimp", "crab", "lobster"], R.DAIRY_FREE: ["dairy", "milk", "cheese", "lactose"],
    R.EGG_FREE: ["egg"], R.SOY_FREE: ["soy"], R.SESAME_FREE: ["sesame"],
    R.GLUTEN_FREE: ["gluten", "wheat", "celiac", "coeliac"], R.VEGAN: ["vegan"], R.VEGETARIAN: ["vegetarian"],
    R.HALAL: ["halal"], R.KOSHER: ["kosher"],
}


def sentence_mentions_allergen(sentence: str, restriction: R) -> bool:
    s = sentence.lower()
    return any(t in s for t in ALLERGEN_NOUNS[restriction])
