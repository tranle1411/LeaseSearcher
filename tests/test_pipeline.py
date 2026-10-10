import json
from pathlib import Path

import pandas as pd
import pytest

from backend.schemas import Dataset, Search
from backend.scoring import recommend
from pipeline.build import build


def test_real_snapshot_demo_and_strict_policies_and_provenance():
    dataset = Dataset.model_validate_json(
        Path("datasets/snapshot.json").read_text(encoding="utf-8")
    )
    assert dataset.listings
    assert dataset.sources["crexi-full-cleaned.csv"]["sha256"]
    assert dataset.eligibility_policy == "demo_assumed"
    demo = recommend(dataset, Search(), "snapshot", ["Vietnamese"])
    assert len(demo.matches) == 10
    assert all(
        m.cost_basis == "advertised_estimate" and m.listing.verification is None
        for m in demo.matches
    )
    strict = dataset.model_copy(update={"eligibility_policy": "strict"})
    assert not recommend(strict, Search(), "snapshot", ["Vietnamese"]).matches
    assert (
        dataset.report["accepted_listings"] + dataset.report["quarantined_rows"]
        == dataset.report["raw_listing_rows"]
    )


def test_import_is_reproducible_and_quarantines_bad_rows(tmp_path, listing):
    data = tmp_path / "Data"
    data.mkdir()
    pd.DataFrame(
        [
            {
                "data-page-selector": "https://www.crexi.com/lease/properties/1/test",
                "full_address": "1 Test St, Test, CA 90001",
                "County": "Los Angeles County",
                "Property Type": "Restaurant",
                "Vacant SqFt": "1,000",
                "has_parking": True,
            },
            {"data-page-selector": "bad", "full_address": "broken"},
        ]
    ).to_csv(data / "crexi-full-cleaned.csv", index=False)
    pd.DataFrame(
        [
            {
                "Address": "1 Test St Test CA 90001",
                "Min_SqFt": 1000,
                "Max_SqFt": 1000,
                "Total_Rent": 2000,
                "Rate": "$2/SF/MO",
            }
        ]
    ).to_excel(data / "CASitesForRent_with_averages.xlsx", index=False)
    pd.DataFrame([{"address": "1 Test St Test CA 90001", "lat": 34, "lon": -118}]).to_csv(
        tmp_path / "geocode_cache.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "restaurant_name": "test",
                "address": "test",
                "zip": "90001",
                "restaurant_type": "vietnamese restaurant",
                "price_mid": 15,
            }
        ]
        * 2
    ).to_csv(data / "ca_restaurants_clean.csv", index=False)
    first = build(tmp_path, tmp_path / "a.json")
    second = build(tmp_path, tmp_path / "b.json")
    assert first == second
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    assert first.report["quarantined_rows"] == 1
    assert first.competition[0].total == 1
    assert first.listings[0].monthly_base_rent == 2000
    assert first.listings[0].verification is None
    for path in (
        data / "crexi-full-cleaned.csv",
        data / "ca_restaurants_clean.csv",
        tmp_path / "geocode_cache.csv",
    ):
        raw = path.read_bytes().replace(b"\r\n", b"\n")
        path.write_bytes(raw.replace(b"\n", b"\r\n"))
    assert build(tmp_path, tmp_path / "crlf.json") == first
    approval = tmp_path / "verified.json"
    approval.write_text(
        json.dumps(
            {first.listings[0].id: {"verification": listing.verification.model_dump(mode="json")}}
        )
    )
    verified = build(tmp_path, tmp_path / "verified-result.json", str(approval))
    assert verified.version != first.version
    assert len(recommend(verified, Search(), "test", ["Vietnamese"]).matches) == 1
    overrides = tmp_path / "bad.json"
    overrides.write_text(json.dumps({"unknown-id": {}}))
    with pytest.raises(ValueError, match="not found"):
        build(tmp_path, tmp_path / "bad-result.json", str(overrides))

    # Original cards join by provider ID even when their address differs.
    pd.DataFrame(
        [
            {
                "image_link": "https://images.example/lease-assets/1/photo",
                "Price": "$24 - $48/SF/YR",
                "Name": "Retail 1,000 SqFt - 2,000 SqFt",
                "address_detail": "Different spelling",
            },
            {
                "image_link": "https://images.example/lease-assets/99/photo",
                "Price": "$999/SF/MO",
                "Name": "Retail 8,000 SqFt",
                "address_detail": "1 Test St Test CA 90001",
            },
        ]
    ).to_excel(data / "CASitesForRent.xlsx", index=False)
    linked = build(tmp_path, tmp_path / "linked.json").listings[0]
    assert (linked.rent_low, linked.rent_high) == (2, 4)
    assert (linked.sqft_min, linked.sqft_max) == (1000, 2000)
    assert "provider listing ID" in linked.rent_source
    raw = pd.read_csv(data / "crexi-full-cleaned.csv")
    raw.loc[0, "Vacant SqFt"] = None
    raw.loc[0, "Total Building SqFt"] = 99999
    raw.to_csv(data / "crexi-full-cleaned.csv", index=False)
    (data / "CASitesForRent.xlsx").unlink()
    pd.DataFrame([{"Address": "unmatched", "Rate": "$2/SF/MO"}]).to_excel(
        data / "CASitesForRent_with_averages.xlsx", index=False
    )
    missing = build(tmp_path, tmp_path / "missing.json").listings[0]
    assert missing.sqft_min is None and missing.sqft_max is None
