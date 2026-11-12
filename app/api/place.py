"""A short "City, Country" for a job card, from the free-text locations sites send.

Sites write the same place many ways: "Ratingen, Nordrhein-Westfalen, Germany",
"Finland, Satakunta, Tampere", "US, California, Folsom", "ES - Madrid, Spain",
"California - San Francisco", "Remote - Germany". The job's own country codes decide
what counts as a country, so "Georgia" in "Atlanta, Georgia, US" stays a state.
"""

import re
from dataclasses import dataclass
from functools import cache

import pycountry

_SPLIT = re.compile(r"\s*,\s*|\s+-\s+")
_REMOTE = re.compile(r"\bremote(?:\s+location)?\b", re.I)
# Office codes like "IND-Bangalore …" or "USA-CA - Promontory B" (Broadcom).
_OFFICE = re.compile(r"^([A-Z]{3})(?:-[A-Z]{2})?(?:\s*-\s*|\s+|$)")
# Short names for the countries that come up most; the rest use pycountry's common name.
_SHORT = {"US": "USA", "GB": "UK", "AE": "UAE", "RU": "Russia", "KR": "South Korea"}
_ALIASES = {
    "prc": "CN",
    "usa": "US",
    "u.s.": "US",
    "united states of america": "US",
    "uk": "GB",
    "england": "GB",
}


@dataclass(frozen=True)
class Place:
    text: str  # "Ratingen, Germany"
    country: str | None  # ISO code of the first location, for its flag
    more: int  # how many other locations
    india: bool
    remote: bool


@cache
def _country_names() -> dict[str, str]:
    names = dict(_ALIASES)
    for c in pycountry.countries:
        for attr in ("name", "common_name", "official_name"):
            if v := getattr(c, attr, None):
                names[v.casefold()] = c.alpha_2
        names[c.alpha_2.casefold()] = c.alpha_2
        names[c.alpha_3.casefold()] = c.alpha_2
    return names


@cache
def _states(code: str) -> frozenset[str]:
    """States and provinces only: a "capital city" (Budapest) or county (Dublin) is a city here."""
    subs = pycountry.subdivisions.get(country_code=code) or []
    return frozenset(s.name.casefold() for s in subs if s.type in ("State", "Province"))


def country_name(code: str) -> str:
    if code in _SHORT:
        return _SHORT[code]
    c = pycountry.countries.get(alpha_2=code)
    return (getattr(c, "common_name", None) or c.name) if c else code


def _country_of(part: str, codes: list[str]) -> str | None:
    code = _country_names().get(part.casefold())
    # Only the job's own countries count, so a state like "Georgia" or "IN" (Indiana) isn't one.
    return code if code and (code in codes or not codes) and len(part) > 1 else None


def _clean(part: str, codes: list[str]) -> str:
    part = re.sub(r"\([^)]*\)", "", part)  # "(do not use) Mumbai …"
    if m := _OFFICE.match(part):
        c = pycountry.countries.get(alpha_3=m.group(1))
        if c and c.alpha_2 in codes:
            part = part[m.end() :]
    part = _REMOTE.sub("", part).strip(" -")
    return part.title() if part.isupper() and len(part) > 3 else part  # "BOURNEMOUTH"


def _city(location: str, codes: list[str]) -> tuple[str | None, str | None]:
    """(city, country code named in the text) for one location string."""
    parts = [p for p in (_clean(s, codes) for s in _SPLIT.split(location)) if p]
    found = [_country_of(p, codes) for p in parts]
    # Only the last part naming a country is the country: in "Jamaica, NY, United States"
    # or "Singapore, Singapore" the earlier one is the city.
    at = max((i for i, c in enumerate(found) if c), default=None)
    country = found[at] if at is not None else None
    rest = [p for i, p in enumerate(parts) if i != at]
    if country or len(rest) > 1:  # state codes: "Abilene, TX, United States"
        rest = [p for p in rest if not re.fullmatch(r"[A-Z]{2}", p)]
    if len(rest) > 1:  # a street address next to a city: "Wien - Donau-City-Straße 7"
        rest = [p for p in rest if not re.search(r"\d", p)] or rest
    if len(rest) > 1 and country is None:  # "California - San Francisco", "O'Fallon, Missouri"
        state_of = codes[0] if codes else None
        states = _states(state_of) if state_of else frozenset()
        rest = [p for p in rest if p.casefold() not in states] or rest
    if not rest:
        return None, country
    return (rest[-1] if at == 0 else rest[0]), country


def place(locations: list[str], codes: list[str], remote_type: str | None) -> Place:
    codes = list(codes or [])
    remote = remote_type == "remote" or any(_REMOTE.search(loc) for loc in locations)
    india = "IN" in codes
    if not locations:
        code = codes[0] if codes else None
        return Place(country_name(code) if code else "", code, 0, india, remote)
    city, named = _city(locations[0], codes)
    code = named or (codes[0] if codes else None)
    country = country_name(code) if code else None
    if city and country and city.casefold() != country.casefold():
        text = f"{city}, {country}"
    else:
        text = city or country or locations[0]
    return Place(text, code, len(locations) - 1, india, remote)
