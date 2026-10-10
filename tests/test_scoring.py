from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.schemas import Dataset, Search, Verification, Weights
from backend.scoring import exclusion_reasons, preference, recommend, scale

CUISINES = ["Vietnamese", "Chinese", "Japanese", "Other"]


def test_strict_unknown_evidence_excluded(listing):
    missing = listing.model_copy(update={"verification": None})
    reasons = exclusion_reasons(missing, Search(), date.today())
    assert "Complete monthly cost unknown" in reasons
    assert "Eligibility unknown, unapproved or expired" in reasons
    assert "Individual lease space unverified" in reasons


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("lat", None, "Map location unknown"),
        ("source_url", None, "Original listing link unknown"),
        ("sqft_min", None, "Available space size unknown"),
        ("sqft_max", 100, "Outside requested space range"),
        ("availability", "unavailable", "Listing unavailable"),
    ],
)
def test_hard_gates(listing, field, value, reason):
    assert reason in exclusion_reasons(
        listing.model_copy(update={field: value}), Search(), date.today()
    )


def test_expired_and_unapproved_and_unconfirmed(listing):
    expired = listing.verification.model_copy(
        update={"valid_until": date.today() - timedelta(days=1)}
    )
    assert exclusion_reasons(
        listing.model_copy(update={"verification": expired}), Search(), date.today()
    )
    unapproved = listing.verification.model_copy(update={"eligible": False})
    assert exclusion_reasons(
        listing.model_copy(update={"verification": unapproved}), Search(), date.today()
    )
    assert "Availability not confirmed within 30 days" in exclusion_reasons(
        listing, Search(hide_unconfirmed=True), date.today()
    )
    confirmed = listing.model_copy(
        update={"availability": "confirmed", "availability_verified_on": date.today()}
    )
    assert not exclusion_reasons(confirmed, Search(hide_unconfirmed=True), date.today())
    assert "Above monthly budget" in exclusion_reasons(listing, Search(budget=2000), date.today())
    assert "Required parking unconfirmed" in exclusion_reasons(
        listing.model_copy(update={"parking": None}), Search(require_parking=True), date.today()
    )


def test_missing_optional_and_constant_neutral(dataset):
    assert scale(100, [100, 100]) == 50
    assert preference(100, [100, 100], "medium") == 50
    empty = dataset.model_copy(update={"areas": (), "competition": ()})
    match = recommend(empty, Search(), "test", CUISINES).matches[0]
    assert match.components["location"] == 50
    assert match.components["competition"] == 50
    assert match.evidence_coverage == 0


def test_cached_percentile_bounds_preserve_ranking_values():
    from backend.scoring import percentile

    values = [1, 3, 5, 9, 15, 25]
    bounds = percentile(values, 0.1), percentile(values, 0.9)
    for value in [None, 0, 1, 5, 14, 25, 30]:
        assert scale(value, values, bounds) == scale(value, values)


def test_budget_monotonic_and_filters_do_not_rescale(dataset):
    search = Search()
    baseline = recommend(dataset, search, "test", CUISINES).matches[0]
    low_budget = recommend(dataset, Search(budget=4000), "test", CUISINES).matches[0]
    assert low_budget.fit_score < baseline.fit_score
    county = recommend(dataset, Search(county="Los Angeles County"), "test", CUISINES).matches[0]
    assert county.fit_score == baseline.fit_score
    assert sum(baseline.contributions.values()) == pytest.approx(baseline.fit_score)


def test_top_ten_tie_order_and_all_cuisines(dataset, listing):
    data = dataset.model_copy(
        update={
            "listings": tuple(
                listing.model_copy(update={"id": f"test-{i:02}"}) for i in reversed(range(15))
            )
        }
    )
    for cuisine in CUISINES:
        result = recommend(data, Search(cuisine=cuisine), "test", CUISINES)
        assert result.total_eligible == 15
        assert len(result.matches) == 10
        assert [m.listing.id for m in result.matches] == [f"test-{i:02}" for i in range(10)]


def test_contract_rejects_bad_ranges_and_empty_weights(dataset):
    with pytest.raises(ValidationError):
        Search(sqft_min=5000, sqft_max=1000)
    with pytest.raises(ValidationError):
        Weights(site=0, location=0, competition=0)
    with pytest.raises(ValidationError):
        Dataset.model_validate({**dataset.model_dump(), "listings": [dataset.listings[0]] * 2})
    with pytest.raises(ValidationError):
        Verification.model_validate(
            {**dataset.listings[0].verification.model_dump(), "monthly_occupancy_cost": None}
        )
