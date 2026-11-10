"""Best-effort country detection from free-text locations.

Career sites write locations as "Bengaluru, India", "IND-Bangalore", "US - Austin, TX",
"KZ - Almaty, Kazakhstan" and so on. Country names come from ISO 3166 (pycountry)
plus common aliases; India also gets city names because it drives alert priority.
"""

import re
from functools import cache

import pycountry

# Names that are also common place names elsewhere (US states, UK islands).
_AMBIGUOUS = {"Georgia", "Jersey"}

_ALIASES: dict[str, list[str]] = {
    "IN": [
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
        r"delhi",
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
    "US": [
        r"united states",
        r"usa?",
        r"u\.s\.",
        r"(?-i:, (CA|TX|WA|NY|MA|NC|GA|OR|CO|IL|AZ|VA|NJ|PA|FL|MN|UT|OH|MI))",
    ],
    "GB": [
        r"united kingdom",
        r"uk",
        r"england",
        r"scotland",
        r"wales",
        r"london",
        r"glasgow",
        r"edinburgh",
        r"manchester",
        r"belfast",
    ],
    "KR": [r"south korea", r"korea", r"seoul"],
    "TW": [r"taiwan", r"taipei", r"hsinchu"],
    "VN": [r"vietnam", r"hanoi", r"ho chi minh"],
    "CZ": [r"czech republic", r"czechia", r"prague", r"brno"],
    "RU": [r"russia"],
    "TR": [r"turkey", r"türkiye", r"istanbul"],
    "HK": [r"hong kong"],
    "AE": [r"uae", r"dubai", r"abu dhabi"],
    "IE": [r"dublin", r"cork"],
    "DE": [r"munich", r"berlin", r"frankfurt", r"hamburg", r"stuttgart"],
    "FR": [r"paris", r"sophia antipolis"],
    "NL": [r"amsterdam", r"eindhoven"],
    "PL": [r"warsaw", r"krak[oó]w", r"wroc[lł]aw"],
    "CA": [r"toronto", r"vancouver", r"montreal", r"ottawa"],
    "SG": [r"singapore"],
    "JP": [r"tokyo", r"osaka"],
    "CN": [r"shanghai", r"beijing", r"shenzhen"],
    "IL": [r"tel aviv", r"yokneam", r"haifa"],
    "AU": [r"sydney", r"melbourne"],
    "IT": [r"rome", r"roma", r"milan", r"milano", r"turin", r"torino"],
    "ES": [r"madrid", r"barcelona"],
    "RO": [r"bucharest"],
    "PH": [r"manila", r"pasig", r"taguig"],
    "EG": [r"cairo"],
    "BR": [r"s[aã]o paulo"],
}


@cache
def _patterns() -> list[tuple[re.Pattern, str]]:
    names: list[tuple[str, str]] = []
    for c in pycountry.countries:
        for attr in ("name", "common_name", "official_name"):
            value = getattr(c, attr, None)
            if value and value not in _AMBIGUOUS:
                names.append((re.escape(value), c.alpha_2))
    for code, aliases in _ALIASES.items():
        names.extend((a, code) for a in aliases)
    # Longest first, so "Papua New Guinea" wins over "Guinea".
    names.sort(key=lambda x: len(x[0]), reverse=True)
    return [(re.compile(rf"(?i)\b{p}\b"), code) for p, code in names]


_PREFIX2 = re.compile(r"^([A-Z]{2}) - ")
_PREFIX3 = re.compile(r"^([A-Z]{3})-")


def country_codes(locations: list[str]) -> list[str]:
    found: set[str] = set()
    for loc in locations:
        if m := _PREFIX2.match(loc):
            if pycountry.countries.get(alpha_2=m.group(1)):
                found.add(m.group(1))
        elif m := _PREFIX3.match(loc):
            if c := pycountry.countries.get(alpha_3=m.group(1)):
                found.add(c.alpha_2)
        rest = loc
        for rx, code in _patterns():
            if rx.search(rest):
                found.add(code)
                rest = rx.sub(" ", rest)
    return sorted(found)
