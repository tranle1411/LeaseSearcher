"""Pure deterministic ranking. No I/O, learned models, or request-relative rescaling."""

from datetime import date
from math import isfinite

from backend.schemas import Dataset, Listing, Match, Results, Search


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def scale(value: float | None, population: list[float], bounds=None) -> float:
    if value is None or not population or not isfinite(value):
        return 50.0
    lo, hi = (
        bounds if bounds is not None else (percentile(population, 0.1), percentile(population, 0.9))
    )
    if lo == hi:
        return 50.0
    return max(0.0, min(100.0, 100 * (value - lo) / (hi - lo)))


def preference(value: float | None, population: list[float], choice: str) -> float:
    if value is None or not population or min(population) == max(population):
        return 50.0
    rank = scale(value, population)
    return {"low": 100 - rank, "medium": 100 - 2 * abs(rank - 50), "high": rank}[choice]


def quoted_cost(listing: Listing, search: Search, policy="strict", pricing="conservative"):
    v = listing.verification
    if (
        v
        and v.eligible
        and v.complete_fees
        and v.lease_space_confirmed
        and v.valid_until >= date.today()
    ):
        return v.monthly_occupancy_cost, None, "verified_total"
    if policy == "strict" or listing.rent_basis is None:
        return None, None, "advertised_estimate"
    if listing.sqft_min is None or listing.sqft_max is None:
        return None, None, "advertised_estimate"
    lo = max(listing.sqft_min, search.sqft_min)
    hi = min(listing.sqft_max, search.sqft_max)
    if lo > hi:
        return None, None, "advertised_estimate"
    area = (lo + hi) / 2 if pricing == "midpoint" else hi
    rate = (
        (listing.rent_low + listing.rent_high) / 2 if pricing == "midpoint" else listing.rent_high
    )
    cost = rate * area if listing.rent_basis == "per_sqft_month" else rate
    return round(cost + (listing.disclosed_monthly_fees or 0), 2), area, "advertised_estimate"


def exclusion_reasons(
    listing: Listing,
    search: Search,
    today: date,
    policy="strict",
    pricing="conservative",
    allow_zip_centroids=False,
) -> list[str]:
    failures = []
    v = listing.verification
    if search.county and listing.county != search.county:
        failures.append("Outside selected county")
    if policy == "strict":
        if not v or not v.eligible or v.valid_until < today:
            failures.append("Eligibility unknown, unapproved or expired")
        if not v or not v.complete_fees or v.monthly_occupancy_cost is None:
            failures.append("Complete monthly cost unknown")
        if not v or not v.lease_space_confirmed:
            failures.append("Individual lease space unverified")
    elif v and (not v.eligible or v.valid_until < today):
        failures.append("Eligibility explicitly unapproved or evidence expired")
    cost, _, _ = quoted_cost(listing, search, policy, pricing)
    if cost is None and policy == "demo_assumed":
        failures.append("Usable advertised rent or size unknown")
    elif cost is not None and cost > search.budget:
        failures.append("Above monthly budget")
    if listing.sqft_min is None or listing.sqft_max is None:
        failures.append("Available space size unknown")
    elif listing.sqft_max < search.sqft_min or listing.sqft_min > search.sqft_max:
        failures.append("Outside requested space range")
    if listing.lat is None:
        failures.append("Map location unknown")
    elif listing.coordinate_precision == "zip_centroid" and not allow_zip_centroids:
        failures.append("Address-level map location unknown")
    if listing.source_url is None:
        failures.append("Original listing link unknown")
    if search.require_parking and listing.parking is not True:
        failures.append("Required parking unconfirmed")
    if listing.availability == "unavailable":
        failures.append("Listing unavailable")
    confirmed_recently = (
        listing.availability == "confirmed"
        and listing.availability_verified_on is not None
        and 0 <= (today - listing.availability_verified_on).days <= 30
    )
    if search.hide_unconfirmed and not confirmed_recently:
        failures.append("Availability not confirmed within 30 days")
    return failures


def recommend(dataset: Dataset, search: Search, mode: str, cuisines: list[str]) -> Results:
    if search.cuisine not in cuisines:
        raise ValueError("Unsupported cuisine; choose one of the listed options")
    counties = {item.county: item for item in dataset.areas}
    competition = {item.postal_code: item for item in dataset.competition}

    # Bounds always use the whole versioned dataset, unaffected by search filters.
    def area_values(key):
        return [getattr(a, key) for a in dataset.areas if getattr(a, key) is not None]

    totals = [float(c.total) for c in dataset.competition]
    same = [float(c.cuisine_counts.get(search.cuisine, 0)) for c in dataset.competition]
    prices = [c.median_price for c in dataset.competition if c.median_price is not None]
    # Sort each reference column once per search, rather than once per eligible listing.
    comp_bounds = [
        (percentile(values, 0.1), percentile(values, 0.9)) if values else None
        for values in (totals, same, prices)
    ]
    weights = search.weights.normalized()
    exclusions: dict[str, int] = {}
    matches = []
    for listing in dataset.listings:
        failures = exclusion_reasons(
            listing,
            search,
            date.today(),
            dataset.eligibility_policy,
            dataset.pricing_policy,
            dataset.allow_zip_centroids,
        )
        if failures:
            for reason in failures:
                exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        cost, assumed_sqft, cost_basis = quoted_cost(
            listing, search, dataset.eligibility_policy, dataset.pricing_policy
        )
        # An overlapping verified offered range can match the requested size.
        size_score = 100.0
        rent_score = max(0.0, 100 * (1 - cost / search.budget))
        area = counties.get(listing.county)
        comp = competition.get(listing.postal_code)
        income = area.household_income if area else None
        population = area.population if area else None
        ethnicity = area.asian_share if area and search.use_ethnicity else None
        location_score = (
            0.3 * preference(income, area_values("household_income"), search.income_preference)
            + 0.4 * preference(population, area_values("population"), search.population_preference)
            + 0.3 * preference(ethnicity, area_values("asian_share"), search.ethnicity_preference)
        )
        total = float(comp.total) if comp else None
        cuisine_count = float(comp.cuisine_counts.get(search.cuisine, 0)) if comp else None
        price = comp.median_price if comp else None
        competition_score = (
            0.3 * (100 - scale(total, totals, comp_bounds[0]))
            + 0.5 * (100 - scale(cuisine_count, same, comp_bounds[1]))
            + 0.2 * scale(price, prices, comp_bounds[2])
        )
        components = {
            "site": 0.5 * rent_score + 0.5 * size_score,
            "location": location_score,
            "competition": competition_score,
        }
        contributions = {k: v * weights[k] for k, v in components.items()}
        features = {
            "monthly_cost_used_for_scoring": cost,
            "household_income": income,
            "county_population": population,
            "asian_share": ethnicity,
            "observed_restaurants_in_zip": total,
            "observed_same_cuisine_in_zip": cuisine_count,
            "median_prepared_price_midpoint": price,
        }
        optional = [income, population, total, cuisine_count, price]
        if search.use_ethnicity:
            optional.append(ethnicity)
        coverage = sum(v is not None for v in optional) / len(optional)
        warnings = list(listing.warnings)
        assumptions = []
        if cost_basis == "advertised_estimate":
            assumptions.extend(
                [
                    "Listing existence and restaurant eligibility are assumed for this demo, not verified.",
                    "The offered range does not confirm that this exact estimated unit size is available.",
                ]
            )
            if listing.disclosed_monthly_fees is None:
                assumptions.append(
                    "Undisclosed occupancy fees are unknown and excluded from this estimate."
                )
            assumptions.append(
                f"Pricing uses the {dataset.pricing_policy} advertised rate and compatible size range."
            )
        if listing.coordinate_precision == "zip_centroid":
            assumptions.append("Map pin is an approximate ZIP center, not the property location.")
        warnings.extend(assumptions)
        warnings.append("Historical listing; confirm current terms with the source.")
        if coverage < 1:
            warnings.append("Missing optional market evidence receives a neutral score of 50.")
        if comp:
            warnings.append(
                "Competition counts reflect observed ZIP coverage, not a complete census."
            )
        if search.cuisine == "Other":
            warnings.append(
                "Other combines uncategorized and other cuisines; this comparison is broad."
            )
        if search.use_ethnicity:
            warnings.append(
                "Asian share is contextual and does not establish demand for this cuisine."
            )
        reasons = (
            f"{'Verified total' if cost_basis == 'verified_total' else 'Estimated advertised'} monthly cost fits the ${search.budget:,.0f} budget.",
            "Reported offered space overlaps the requested size range.",
        )
        matches.append(
            Match(
                rank=0,
                listing=listing,
                fit_score=round(sum(contributions.values()), 2),
                components=components,
                contributions=contributions,
                features=features,
                evidence_coverage=round(coverage * 100, 1),
                reasons=reasons,
                warnings=tuple(warnings),
                effective_monthly_cost=cost,
                cost_basis=cost_basis,
                assumed_sqft=assumed_sqft,
                assumptions=tuple(assumptions),
            )
        )
    matches.sort(key=lambda item: (-item.fit_score, item.listing.id))
    ranked = tuple(m.model_copy(update={"rank": i + 1}) for i, m in enumerate(matches[:10]))
    return Results(
        dataset_version=dataset.version,
        eligibility_policy=dataset.eligibility_policy,
        pricing_policy=dataset.pricing_policy,
        mode=mode,
        matches=ranked,
        total_eligible=len(matches),
        considered=len(dataset.listings),
        exclusions=exclusions,
        weights=weights,
        search=search,
    )
