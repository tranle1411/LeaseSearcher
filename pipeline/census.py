"""Fetch aggregate ACS data with provenance; no microdata or scraping."""

import argparse
import json
import os
from pathlib import Path

import httpx

from backend.schemas import Area


def fetch(year, output):
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        raise SystemExit("Set CENSUS_API_KEY (request one at api.census.gov/data/key_signup.html)")
    variables = "NAME,B01003_001E,B19013_001E,B02001_005E,B01003_001M,B19013_001M,B02001_005M"
    response = httpx.get(
        f"https://api.census.gov/data/{year}/acs/acs5",
        params={"get": variables, "for": "county:*", "in": "state:06", "key": key},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    rows = [dict(zip(data[0], row)) for row in data[1:]]

    def estimate(row, name):
        value = float(row[name]) if row.get(name) is not None else None
        return value if value is not None and value >= 0 else None

    areas = []
    for row in rows:
        population = estimate(row, "B01003_001E")
        asian = estimate(row, "B02001_005E")
        areas.append(
            Area(
                county=row["NAME"].split(",")[0],
                geoid=row["state"] + row["county"],
                vintage=f"{year} ACS 5-year",
                population=population,
                household_income=estimate(row, "B19013_001E"),
                asian_share=100 * asian / population if population and asian is not None else None,
                margins_of_error={
                    v: estimate(row, v) for v in variables.split(",") if v.endswith("M")
                },
            )
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([a.model_dump(mode="json") for a in areas], indent=2), encoding="utf-8"
    )
    print(f"Saved {len(areas)} county aggregates to {output}; rebuild snapshot with --areas")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--output", type=Path, default=Path(".local/acs-2024.json"))
    args = parser.parse_args()
    fetch(args.year, args.output)
