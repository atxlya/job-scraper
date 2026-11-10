"""Best-effort country detection from free-text locations.

Career sites write locations as "Bengaluru, India", "IND-Bangalore", "US - Austin, TX"
and so on. India gets extra city names because it drives alert priority.
"""

import re

_PATTERNS: dict[str, list[str]] = {
    "IN": [
        r"india",
        r"\bind\b",
        r"bengaluru",
        r"bangalore",
        r"pune",
        r"hyderabad",
        r"chennai",
        r"mumbai",
        r"gurugram",
        r"gurgaon",
        r"noida",
        r"new delhi",
        r"\bdelhi\b",
        r"kolkata",
        r"ahmedabad",
        r"kochi",
        r"thiruvananthapuram",
        r"trivandrum",
        r"coimbatore",
        r"jaipur",
        r"mysuru",
        r"mysore",
        r"indore",
        r"chandigarh",
        r"vadodara",
    ],
    "US": [r"united states", r"\busa?\b", r"\bu\.s\.", r", (ca|tx|wa|ny|ma|nc|ga|or|co|il|az)\b"],
    "GB": [r"united kingdom", r"\buk\b", r"england", r"scotland", r"london", r"glasgow"],
    "IE": [r"ireland", r"dublin"],
    "DE": [r"germany", r"deutschland", r"munich", r"berlin", r"frankfurt"],
    "FR": [r"france", r"paris"],
    "NL": [r"netherlands", r"amsterdam"],
    "PL": [r"poland", r"warsaw", r"krak[oó]w"],
    "CA": [r"canada", r"toronto", r"vancouver", r"montreal"],
    "SG": [r"singapore"],
    "JP": [r"japan", r"tokyo"],
    "CN": [r"china", r"shanghai", r"beijing", r"shenzhen"],
    "TW": [r"taiwan", r"taipei"],
    "KR": [r"korea", r"seoul"],
    "IL": [r"israel", r"tel aviv", r"yokneam"],
    "AU": [r"australia", r"sydney", r"melbourne"],
    "AE": [r"united arab emirates", r"dubai", r"abu dhabi"],
    "MX": [r"mexico"],
    "BR": [r"brazil", r"s[aã]o paulo"],
}
_COMPILED = {cc: re.compile("|".join(p), re.IGNORECASE) for cc, p in _PATTERNS.items()}


def country_codes(locations: list[str]) -> list[str]:
    found = {cc for loc in locations for cc, rx in _COMPILED.items() if rx.search(loc)}
    return sorted(found)
