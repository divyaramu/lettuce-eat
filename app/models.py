from enum import Enum
from pydantic import BaseModel, Field, field_validator

from .security import clean_text


class Restriction(str, Enum):
    PEANUT_FREE = "peanut_free"
    TREE_NUT_FREE = "tree_nut_free"
    SHELLFISH_FREE = "shellfish_free"
    DAIRY_FREE = "dairy_free"
    EGG_FREE = "egg_free"
    SOY_FREE = "soy_free"
    SESAME_FREE = "sesame_free"
    GLUTEN_FREE = "gluten_free"
    VEGAN = "vegan"
    VEGETARIAN = "vegetarian"
    HALAL = "halal"
    KOSHER = "kosher"


ALLERGENS = {Restriction.PEANUT_FREE, Restriction.TREE_NUT_FREE, Restriction.SHELLFISH_FREE,
             Restriction.DAIRY_FREE, Restriction.EGG_FREE, Restriction.SOY_FREE,
             Restriction.SESAME_FREE, Restriction.GLUTEN_FREE}


class Member(BaseModel):
    id: str
    nickname: str
    restrictions: list[str | Restriction] = Field(default_factory=list)

    @field_validator("nickname")
    @classmethod
    def _nick(cls, v: str) -> str:
        v = clean_text(v, 30)
        if not v:
            raise ValueError("nickname required")
        return v


class Group(BaseModel):
    id: str
    join_token: str
    area: str = "Seattle, WA"
    lat: float | None = None
    lon: float | None = None
    radius_km: float = 2.0
    members: list[Member] = Field(default_factory=list)


class Tier(str, Enum):
    OFFICIAL = "official_verified"
    COMMUNITY = "community_verified"
    QUESTIONABLE = "questionable"
    UNSAFE = "reported_unsafe"


class SourceKind(str, Enum):
    OFFICIAL = "official"
    REDDIT = "reddit"
    BLOG = "blog"
    REVIEW = "review"
    SOCIAL = "social"


class Evidence(BaseModel):
    """One verifiable claim: a verbatim quote that was re-found in the fetched page text."""
    restriction: Restriction
    stance: str  # "supports" | "warns"
    quote: str
    url: str
    source_kind: SourceKind
    dish: str | None = None
    verified_quote: bool = True


class RestrictionResult(BaseModel):
    restriction: Restriction
    tier: Tier
    evidence: list[Evidence] = Field(default_factory=list)
    note: str = ""


class Venue(BaseModel):
    name: str
    address: str = ""
    website: str | None = None
    phone: str | None = None


class VenueReport(BaseModel):
    venue: Venue
    results: list[RestrictionResult]
    score: float
    summary: str


class GroupReport(BaseModel):
    group_id: str
    generated_at: str
    venues: list[VenueReport]
    disclaimer: str = ("Menus change and kitchens vary. For allergies, always confirm with the "
                       "restaurant before ordering. Tiers show how well-sourced a claim is, not a guarantee.")
