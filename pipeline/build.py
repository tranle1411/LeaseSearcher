"""Deterministic, offline-first import. Never imports the person-level IPUMS file."""

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from backend.schemas import Area, Competition, Dataset, Listing
from pipeline.review import read_reviews
from pipeline.crexi import advertised_size, provider_id, rent_range


def normalized(value):
    value = re.sub(r"[^a-z0-9 ]", " ", str(value).lower())
    for long, short in {
        "street": "st",
        "avenue": "ave",
        "boulevard": "blvd",
        "road": "rd",
        "drive": "dr",
        "suite": "ste",
    }.items():
        value = re.sub(rf"\b{long}\b", short, value)
    return " ".join(value.split())


def number(value):
    try:
        result = float(str(value).replace(",", ""))
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def text(value):
    return str(value).strip() if pd.notna(value) else ""


def build(root: Path, output: Path, verifications=None, areas=None):
    config_path = root / "datasets/build-config.json"
    policy = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    allowed_policy = {"eligibility_policy", "pricing_policy", "allow_zip_centroids"}
    if set(policy) - allowed_policy:
        raise ValueError("Unknown build policy fields")
    paths = [
        root / "Data/crexi-full-cleaned.csv",
        root / "Data/CASitesForRent_with_averages.xlsx",
        root / "Data/ca_restaurants_clean.csv",
        root / "geocode_cache.csv",
    ]
    wide = root / "Data/crexi-com-2025-11-07_wide.csv"
    cards_path = root / "Data/CASitesForRent.xlsx"
    zip_path = root / "Data/ca_zip_centroids.csv"
    for path in (wide, cards_path, zip_path):
        if path.exists():
            paths.append(path)
    sources = {
        path.name: {
            "sha256": hashlib.sha256(
                path.read_bytes().replace(b"\r\n", b"\n")
                if path.suffix == ".csv"
                else path.read_bytes()
            ).hexdigest(),
            "hash_encoding": "CSV bytes with LF newlines"
            if path.suffix == ".csv"
            else "Original binary bytes",
            "collection_period": "September–December 2025",
            "permission_status": "Public visibility reported; redistribution terms not verified",
        }
        for path in paths
    }
    overrides = {}
    if verifications:
        overrides = (
            read_reviews(verifications)
            if Path(verifications).suffix == ".xlsx"
            else json.loads(Path(verifications).read_text(encoding="utf-8"))
        )
    area_rows = (
        [Area.model_validate(row) for row in json.loads(Path(areas).read_text(encoding="utf-8"))]
        if areas
        else []
    )
    sources["verification"] = {
        "sha256": hashlib.sha256(json.dumps(overrides, sort_keys=True).encode()).hexdigest()
    }
    sources["areas"] = {
        "sha256": hashlib.sha256(
            json.dumps([a.model_dump(mode="json") for a in area_rows], sort_keys=True).encode()
        ).hexdigest()
    }
    rents = defaultdict(list)
    for row in pd.read_excel(paths[1]).to_dict("records"):
        rents[normalized(row["Address"])].append(row)
    coords = {normalized(row["address"]): row for row in pd.read_csv(paths[3]).to_dict("records")}
    cards = defaultdict(list)
    if cards_path.exists():
        for row in pd.read_excel(cards_path).to_dict("records"):
            identity = provider_id(row.get("image_link"))
            if identity:
                cards[identity].append(row)
    zip_coords = {}
    if zip_path.exists():
        zip_coords = {
            str(row["zip"]).zfill(5): row
            for row in pd.read_csv(zip_path, dtype={"zip": str}).to_dict("records")
        }
    listings, quarantine, seen, matched = [], [], set(), 0
    raw_source = wide if wide.exists() else paths[0]
    raw = pd.read_csv(raw_source).to_dict("records")
    for index, row in enumerate(raw, 2):
        url = text(row["data-page-selector"])
        identity = hashlib.sha256(url.encode()).hexdigest()[:16]
        address = text(row["full_address"])
        try:
            if not url.startswith("https://www.crexi.com/lease/properties/"):
                raise ValueError("Missing or invalid provider listing URL")
            if identity in seen:
                raise ValueError("Duplicate source listing identity")
            seen.add(identity)
            zip_match = re.search(r"\b(9\d{4})(?:-\d{4})?\s*$", address)
            if not zip_match:
                raise ValueError("Missing California ZIP code")
            warnings = []
            county = text(row["County"])
            if not county:
                county = "Unknown county"
                warnings.append("County missing from source; not inferred from ZIP code.")
            else:
                county = re.sub(r"\s+county$", "", county, flags=re.IGNORECASE).strip() + " County"
            candidates = rents.get(normalized(address), [])
            rent = candidates[0] if len(candidates) == 1 else {}
            linked_cards = cards.get(provider_id(url), [])
            parsed_cards = [rent_range(card.get("Price")) for card in linked_cards]
            parsed_cards = [item for item in parsed_cards if item]
            card_rates = {
                (item["rent_basis"], item["rent_low"], item["rent_high"]) for item in parsed_cards
            }
            if len(card_rates) == 1:
                rate = parsed_cards[0]
                rent_source = "Original Crexi card matched by provider listing ID"
            elif len(card_rates) > 1:
                rate = None
                rent_source = None
                warnings.append(
                    "Conflicting advertised rates for the same listing ID; rent not inferred."
                )
            else:
                rate = rent_range(rent.get("Rate"))
                rent_source = (
                    "Unique normalized address match to prepared rent workbook" if rate else None
                )
            matched += bool(rate)
            if not rate:
                warnings.append("No unambiguous advertised rate with usable units.")
            coordinate = coords.get(normalized(address), {})
            if not coordinate:
                for card in linked_cards:
                    coordinate = coords.get(normalized(card.get("address_detail")), {})
                    if coordinate:
                        break
            lat, lon = number(coordinate.get("lat")), coordinate.get("lon")
            # Longitude is negative, so it needs a separate finite check.
            lon = float(lon) if lon is not None and pd.notna(lon) else None
            if lat is None or lon is None:
                lat = lon = None
            precision = "address"
            coordinate_source = (
                "legacy address geocode cache; not independently verified" if lat else None
            )
            if lat is None and policy.get("allow_zip_centroids") and zip_match[1] in zip_coords:
                centroid = zip_coords[zip_match[1]]
                lat, lon = float(centroid["lat"]), float(centroid["lon"])
                precision = "zip_centroid"
                coordinate_source = "ZIP center from supplied uszips.csv; approximate area only"
            vacant = number(row.get("Vacant SqFt"))
            card_sizes = {advertised_size(card.get("Name")) for card in linked_cards}
            card_sizes.discard((None, None))
            if len(card_sizes) == 1:
                sqft_min, sqft_max = next(iter(card_sizes))
                size_source = "Original Crexi card matched by provider listing ID"
            elif len(card_sizes) > 1:
                sqft_min = sqft_max = None
                size_source = None
                warnings.append("Conflicting advertised size ranges for the same listing ID.")
            else:
                sqft_min = number(row.get("Minimum Divisible SqFt"))
                sqft_max = number(row.get("Max Contiguous SqFt"))
                if sqft_min and sqft_max:
                    size_source = "Crexi minimum divisible / maximum contiguous space"
                elif number(rent.get("Min_SqFt")) and number(rent.get("Max_SqFt")):
                    sqft_min, sqft_max = number(rent["Min_SqFt"]), number(rent["Max_SqFt"])
                    size_source = "Unique normalized address match to prepared size workbook"
                else:
                    sqft_min = sqft_max = vacant
                    size_source = (
                        "Crexi reported vacant area; unit availability assumed" if vacant else None
                    )
            payload = {
                "id": identity,
                "source_url": url,
                "name": address.split(",")[0],
                "address": address,
                "county": county,
                "postal_code": zip_match[1],
                "sqft_min": sqft_min,
                "sqft_max": sqft_max,
                "size_source": size_source,
                "monthly_base_rent": number(rent.get("Total_Rent")),
                **(rate or {}),
                "rent_source": rent_source,
                "advertised_restaurant": "restaurant" in text(row["Property Type"]).lower(),
                # False in this manually cleaned field does not establish absence.
                "parking": True if str(row["has_parking"]).lower() == "true" else None,
                "lat": lat,
                "lon": lon,
                "coordinate_source": coordinate_source,
                "coordinate_precision": precision,
                "zoning": text(row.get("Zoning")) or None,
                "source_listed_on": pd.to_datetime(
                    row.get("Date Listed"), format="%d-%b-%y", errors="coerce"
                )
                .date()
                .isoformat()
                if pd.notna(
                    pd.to_datetime(row.get("Date Listed"), format="%d-%b-%y", errors="coerce")
                )
                else None,
                "source_updated_on": pd.to_datetime(
                    row.get("Last Updated"), format="%d-%b-%y", errors="coerce"
                )
                .date()
                .isoformat()
                if pd.notna(
                    pd.to_datetime(row.get("Last Updated"), format="%d-%b-%y", errors="coerce")
                )
                else None,
                "warnings": warnings,
            }
            override = overrides.get(identity, {})
            allowed = {
                "verification",
                "unit",
                "sqft_min",
                "sqft_max",
                "lat",
                "lon",
                "coordinate_source",
                "parking",
                "zoning",
                "availability",
                "availability_verified_on",
            }
            if set(override) - allowed:
                raise ValueError("Verification contains unsupported fields")
            payload.update(override)
            listings.append(Listing.model_validate(payload))
        except (ValueError, TypeError) as error:
            quarantine.append(
                {"source": raw_source.name, "row": index, "id": identity, "reason": str(error)}
            )
    unknown = set(overrides) - seen
    if unknown:
        raise ValueError(f"Verification IDs not found in source: {sorted(unknown)}")
    # No false statewide zero counts: only ZIPs with observed restaurant records exist.
    groups = defaultdict(list)
    restaurant_seen = set()
    for row in pd.read_csv(paths[2], dtype={"zip": str}).to_dict("records"):
        postal = text(row["zip"]).split(".")[0].zfill(5)
        key = normalized(row["restaurant_name"]), normalized(row["address"])
        if key in restaurant_seen or not re.fullmatch(r"9\d{4}", postal):
            continue
        restaurant_seen.add(key)
        groups[postal].append(row)
    competition = []
    for postal, rows in sorted(groups.items()):
        counts = Counter()
        prices = []
        for row in rows:
            category = text(row["restaurant_type"]).lower()
            classified = False
            for cuisine in (
                "vietnamese",
                "chinese",
                "japanese",
                "korean",
                "thai",
                "indian",
                "filipino",
                "indonesian",
                "malaysian",
                "taiwanese",
            ):
                if cuisine in category or (cuisine == "japanese" and "sushi" in category):
                    counts[cuisine.title()] += 1
                    classified = True
            if not classified:
                counts["Other"] += 1
            price = number(row["price_mid"])
            if price:
                prices.append(price)
        competition.append(
            Competition(
                postal_code=postal,
                total=len(rows),
                cuisine_counts=dict(counts),
                median_price=float(pd.Series(prices).median()) if prices else None,
            )
        )
    report = {
        "parser_version": "historical-v2.1.0",
        "listing_source": raw_source.name,
        "raw_listing_rows": len(raw),
        "accepted_listings": len(listings),
        "quarantined_rows": len(quarantine),
        "unique_rent_matches": matched,
        "mapped_listings": sum(item.lat is not None for item in listings),
        "address_coordinates": sum(
            item.lat is not None and item.coordinate_precision == "address" for item in listings
        ),
        "zip_center_coordinates": sum(
            item.coordinate_precision == "zip_centroid" for item in listings
        ),
        "unknown_county_listings": sum(item.county == "Unknown county" for item in listings),
        "verified_listings": sum(item.verification is not None for item in listings),
        "restaurant_records_after_deduplication": len(restaurant_seen),
        "demographics": "ACS county aggregates" if area_rows else "Unavailable; neutral scores",
        "quarantine": quarantine,
        "limitations": [
            "Historical partial coverage from one listing provider.",
            "Restaurant observations are not foot traffic or a complete competitor census.",
            "Legacy rent averages do not establish unit-level total occupancy costs.",
        ],
    }
    content = {
        **policy,
        "sources": sources,
        "listings": [item.model_dump(mode="json") for item in sorted(listings, key=lambda x: x.id)],
        "competition": [item.model_dump(mode="json") for item in competition],
        "areas": [
            item.model_dump(mode="json") for item in sorted(area_rows, key=lambda x: x.county)
        ],
        "report": report,
    }
    version = "ca-" + hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
    dataset = Dataset(version=version, **content)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Replace on the same filesystem only after the entire validated artifact is written.
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=output.parent,
        suffix=".json.tmp",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(dataset.model_dump_json(indent=2))
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(
        json.dumps(
            {"version": version, **{k: v for k, v in report.items() if k != "quarantine"}}, indent=2
        )
    )
    return dataset


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("datasets/snapshot.json"))
    parser.add_argument("--verifications")
    parser.add_argument("--areas")
    args = parser.parse_args()
    build(args.root, args.output, args.verifications, args.areas)
