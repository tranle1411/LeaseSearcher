import os
from datetime import date, timedelta

import pytest

from backend.schemas import Area, Competition, Dataset, Listing, Verification


@pytest.fixture
def listing():
    today = date.today()
    return Listing(
        id="fixture-1",
        name="TEST FIXTURE ONLY",
        address="Test address, CA 90001",
        county="Los Angeles County",
        postal_code="90001",
        source_url="https://example.com/test-listing",
        sqft_min=1000,
        sqft_max=1500,
        lat=34.05,
        lon=-118.24,
        parking=True,
        verification=Verification(
            eligible=True,
            complete_fees=True,
            lease_space_confirmed=True,
            monthly_occupancy_cost=3000,
            verified_on=today,
            valid_until=today + timedelta(days=30),
            verified_by="Automated test",
            evidence="TEST DATA ONLY - no actual eligibility",
        ),
    )


@pytest.fixture
def dataset(listing):
    return Dataset(
        version="test-fixture",
        sources={"test": {"synthetic": True}},
        listings=(listing,),
        areas=(
            Area(
                county=listing.county,
                geoid="06037",
                vintage="test",
                population=1000,
                household_income=100000,
                asian_share=20,
            ),
        ),
        competition=(
            Competition(
                postal_code="90001", total=5, cuisine_counts={"Vietnamese": 2}, median_price=20
            ),
        ),
    )


@pytest.fixture
def client(monkeypatch, dataset, tmp_path):
    from fastapi.testclient import TestClient
    from backend.main import app

    path = tmp_path / "snapshot.json"
    path.write_text(dataset.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("SNAPSHOT_PATH", str(path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def postgres_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
    return url
