"""Explicit Crexi adapters: preserve ranges and never treat building area as a suite."""

import re


NUMBER = r"\d+(?:\.\d+)?"


def provider_id(value):
    match = re.search(r"/(?:properties|lease-assets)/(\d+)(?:/|$)", str(value))
    return match[1] if match else None


def rent_range(value):
    """Return monthly per-SF or flat rates; unknown/ambiguous units stay unknown."""
    raw = str(value).strip()
    cleaned = raw.upper().replace(",", "").replace(" ", "").replace("$", "")
    match = re.fullmatch(rf"({NUMBER})(?:-({NUMBER}))?/(SF/)?(MO|YR|MONTH|YEAR)", cleaned)
    if not match:
        return None
    low, high = float(match[1]), float(match[2] or match[1])
    if low <= 0 or high < low:
        return None
    divisor = 12 if match[4] in ("YR", "YEAR") else 1
    return {
        "rent_basis": "per_sqft_month" if match[3] else "monthly",
        "rent_low": low / divisor,
        "rent_high": high / divisor,
        "advertised_price": raw,
    }


def advertised_size(value):
    cleaned = str(value).lower().replace(",", "")
    unit = r"(?:sq\s*\.?\s*ft\.?|square\s*feet)"
    matches = re.findall(rf"({NUMBER})(?:\s*-\s*({NUMBER}))?\s*{unit}", cleaned)
    values = [float(v) for pair in matches for v in pair if v and float(v) > 0]
    return (min(values), max(values)) if values else (None, None)
