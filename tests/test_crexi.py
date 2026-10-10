import pytest

from pipeline.crexi import advertised_size, provider_id, rent_range


def test_provider_id_links_cards_without_guessing_urls():
    assert provider_id("https://www.crexi.com/lease/properties/123/california-test") == "123"
    assert provider_id("https://images.crexi.com/lease-assets/123/image.jpg") == "123"
    assert provider_id("https://example.com/arbitrary-address") is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("$1.70 - $3.73/SF/MO", (1.7, 3.73, "per_sqft_month")),
        ("$24/SF/YR", (2, 2, "per_sqft_month")),
        ("$3,000/MO", (3000, 3000, "monthly")),
        ("$12,000/YR", (1000, 1000, "monthly")),
    ],
)
def test_explicit_rent_conversion(text, expected):
    parsed = rent_range(text)
    assert (parsed["rent_low"], parsed["rent_high"], parsed["rent_basis"]) == expected


@pytest.mark.parametrize("text", ["Undisclosed Rate", "$5", "$0/SF/MO", "$3 - $2/SF/MO"])
def test_unknown_or_invalid_rent_is_not_invented(text):
    assert rent_range(text) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Retail · 2 spaces available · 770 SqFt - 1,370 SqFt", (770, 1370)),
        ("Retail · 800 - 1,380 sq. ft.", (800, 1380)),
        ("Single tenant · 4,355 SqFt", (4355, 4355)),
        ("2 spaces available", (None, None)),
    ],
)
def test_only_explicit_square_footage_is_parsed(text, expected):
    assert advertised_size(text) == expected
