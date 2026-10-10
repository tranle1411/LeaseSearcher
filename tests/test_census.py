import json

import httpx
import pytest

from pipeline.census import fetch


def test_census_requires_key_and_treats_sentinels_as_unknown(monkeypatch, tmp_path):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="CENSUS_API_KEY"):
        fetch(2024, tmp_path / "missing.json")
    monkeypatch.setenv("CENSUS_API_KEY", "test-only")
    data = [
        [
            "NAME",
            "B01003_001E",
            "B19013_001E",
            "B02001_005E",
            "B01003_001M",
            "B19013_001M",
            "B02001_005M",
            "state",
            "county",
        ],
        [
            "Test County, California",
            "1000",
            "-666666666",
            "200",
            "50",
            "-555555555",
            "25",
            "06",
            "001",
        ],
    ]
    response = httpx.Response(
        200, json=data, request=httpx.Request("GET", "https://api.census.gov")
    )
    monkeypatch.setattr("pipeline.census.httpx.get", lambda *args, **kwargs: response)
    output = tmp_path / "acs.json"
    fetch(2024, output)
    area = json.loads(output.read_text())[0]
    assert area["household_income"] is None
    assert area["population"] == 1000
    assert area["asian_share"] == 20
    assert area["margins_of_error"]["B19013_001M"] is None
