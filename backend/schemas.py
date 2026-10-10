"""Validated contracts shared by ingestion, persistence, ranking and OpenAPI."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Verification(Contract):
    eligible: bool
    complete_fees: bool
    lease_space_confirmed: bool
    monthly_occupancy_cost: float | None = Field(default=None, gt=0)
    verified_on: date
    valid_until: date
    verified_by: str = Field(min_length=2, max_length=120)
    evidence: str = Field(min_length=5, max_length=500)

    @model_validator(mode="after")
    def dates_and_cost(self):
        if self.verified_on > date.today() or self.valid_until < self.verified_on:
            raise ValueError("Verification dates are invalid")
        if self.complete_fees and self.monthly_occupancy_cost is None:
            raise ValueError("Complete fees require a known total monthly occupancy cost")
        return self


class Listing(Contract):
    id: str
    source_id: str = "crexi-historical"
    source_url: HttpUrl | None = None
    name: str
    address: str
    county: str
    postal_code: str = Field(pattern=r"^\d{5}$")
    unit: str | None = None
    sqft_min: float | None = Field(default=None, gt=0)
    sqft_max: float | None = Field(default=None, gt=0)
    monthly_base_rent: float | None = Field(default=None, gt=0)
    advertised_price: str | None = None
    rent_basis: Literal["per_sqft_month", "monthly"] | None = None
    rent_low: float | None = Field(default=None, gt=0)
    rent_high: float | None = Field(default=None, gt=0)
    rent_source: str | None = None
    size_source: str | None = None
    disclosed_monthly_fees: float | None = Field(default=None, ge=0)
    lat: float | None = Field(default=None, ge=32, le=42.1)
    lon: float | None = Field(default=None, ge=-124.6, le=-114)
    coordinate_source: str | None = None
    coordinate_precision: Literal["address", "zip_centroid"] = "address"
    advertised_restaurant: bool | None = None
    parking: bool | None = None
    zoning: str | None = None
    availability: Literal["unconfirmed", "confirmed", "unavailable"] = "unconfirmed"
    availability_verified_on: date | None = None
    observed_on: date | None = None
    source_listed_on: date | None = None
    source_updated_on: date | None = None
    verification: Verification | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def paired_values(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("Coordinates must be supplied as a pair")
        if self.sqft_min and self.sqft_max and self.sqft_min > self.sqft_max:
            raise ValueError("Space minimum exceeds maximum")
        if self.rent_basis is not None:
            if self.rent_low is None or self.rent_high is None or self.rent_low > self.rent_high:
                raise ValueError("Rent basis requires a valid ordered rate range")
        if self.availability == "confirmed" and not self.availability_verified_on:
            raise ValueError("Confirmed availability requires a verification date")
        return self


class Area(Contract):
    county: str
    geoid: str
    vintage: str
    population: float | None = Field(default=None, ge=0)
    household_income: float | None = Field(default=None, ge=0)
    asian_share: float | None = Field(default=None, ge=0, le=100)
    margins_of_error: dict[str, float | None] = Field(default_factory=dict)


class Competition(Contract):
    postal_code: str
    total: int = Field(ge=0)
    cuisine_counts: dict[str, int]
    median_price: float | None = Field(default=None, ge=0)


class Dataset(Contract):
    version: str
    schema_version: Literal[1] = 1
    collection_period: str = "September–December 2025"
    sources: dict[str, dict]
    listings: tuple[Listing, ...]
    areas: tuple[Area, ...] = ()
    competition: tuple[Competition, ...] = ()
    report: dict = Field(default_factory=dict)
    eligibility_policy: Literal["strict", "demo_assumed"] = "strict"
    pricing_policy: Literal["conservative", "midpoint"] = "conservative"
    allow_zip_centroids: bool = False

    @model_validator(mode="after")
    def unique_keys(self):
        for items, key in [
            (self.listings, "id"),
            (self.areas, "county"),
            (self.competition, "postal_code"),
        ]:
            values = [getattr(item, key) for item in items]
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate dataset key: {key}")
        return self


class Weights(Contract):
    site: float = Field(default=40, ge=0, le=100)
    location: float = Field(default=40, ge=0, le=100)
    competition: float = Field(default=20, ge=0, le=100)

    @model_validator(mode="after")
    def nonzero(self):
        if self.site + self.location + self.competition == 0:
            raise ValueError("At least one priority must be greater than zero")
        return self

    def normalized(self):
        total = self.site + self.location + self.competition
        return {key: value / total for key, value in self.model_dump().items()}


class Search(Contract):
    cuisine: str = Field(default="Vietnamese", max_length=60)
    county: str | None = Field(default=None, max_length=80)
    budget: float = Field(default=10000, gt=0, le=1000000)
    sqft_min: float = Field(default=500, gt=0, le=200000)
    sqft_max: float = Field(default=4000, gt=0, le=200000)
    income_preference: Literal["low", "medium", "high"] = "medium"
    population_preference: Literal["low", "medium", "high"] = "high"
    use_ethnicity: bool = False
    ethnicity_preference: Literal["low", "medium", "high"] = "high"
    require_parking: bool = False
    hide_unconfirmed: bool = False
    weights: Weights = Field(default_factory=Weights)
    dataset_version: str | None = Field(default=None, max_length=80)
    evaluated_on: date | None = None

    @model_validator(mode="after")
    def size_range(self):
        if self.sqft_min > self.sqft_max:
            raise ValueError("Minimum space must not exceed maximum space")
        return self


class Match(Contract):
    rank: int
    listing: Listing
    fit_score: float
    components: dict[str, float]
    contributions: dict[str, float]
    features: dict[str, float | None]
    evidence_coverage: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    effective_monthly_cost: float = Field(gt=0)
    cost_basis: Literal["verified_total", "advertised_estimate"]
    assumed_sqft: float | None = None
    assumptions: tuple[str, ...] = ()


class Results(Contract):
    dataset_version: str
    evaluated_on: date = Field(default_factory=date.today)
    scoring_version: str = "final-deck-corrected-v2"
    eligibility_policy: Literal["strict", "demo_assumed"] = "strict"
    pricing_policy: Literal["conservative", "midpoint"] = "conservative"
    mode: str
    matches: tuple[Match, ...]
    total_eligible: int
    considered: int
    exclusions: dict[str, int]
    exclusion_rule: str = "Counts overlap: one listing may fail several requirements."
    weights: dict[str, float]
    search: Search
