import pytest

from app.adapters.geo import country_codes


@pytest.mark.parametrize(
    ("locations", "expected"),
    [
        (["Bengaluru, India"], ["IN"]),
        (["IND-Bangalore"], ["IN"]),
        (["Pune"], ["IN"]),
        (["US - Austin, TX"], ["US"]),
        (["United States of America"], ["US"]),
        (["London, United Kingdom", "Pune, India"], ["GB", "IN"]),
        (["Remote"], []),
        (["Santa Clara, CA, United States", "Hyderabad, Telangana, India"], ["IN", "US"]),
    ],
)
def test_country_codes(locations, expected):
    assert country_codes(locations) == expected
