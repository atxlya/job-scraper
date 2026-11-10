"""Rule-based first pass: is it an internship, is it a tech role? None = ask Gemini."""

import re
from pathlib import Path
from typing import NamedTuple

import yaml

from app.adapters.base import RawJob


class Classification(NamedTuple):
    is_internship: bool | None
    is_tech: bool | None


class Keywords(NamedTuple):
    internship: re.Pattern
    not_internship: re.Pattern
    maybe_internship: re.Pattern
    tech: re.Pattern
    non_tech: re.Pattern


def _rx(words: list[str], case_sensitive: list[str] | None = None) -> re.Pattern:
    parts = [rf"(?i:\b(?:{w})\b)" for w in words]
    parts += [rf"\b(?:{w})\b" for w in case_sensitive or []]
    return re.compile("|".join(parts) or r"(?!x)x")


def load_keywords(path: str | Path) -> Keywords:
    data = yaml.safe_load(Path(path).read_text())
    return Keywords(
        internship=_rx(data["internship"]),
        not_internship=_rx(data.get("not_internship", [])),
        maybe_internship=_rx(data.get("maybe_internship", [])),
        tech=_rx(data["tech"], data.get("tech_case_sensitive", [])),
        non_tech=_rx(data.get("non_tech", [])),
    )


def classify(raw: RawJob, kw: Keywords) -> Classification:
    title = kw.not_internship.sub(" ", raw.title)
    if raw.platform_flags.get("intern") or kw.internship.search(title):
        is_internship = True
    elif kw.maybe_internship.search(title):
        is_internship = None
    else:
        is_internship = False

    tech, non_tech = bool(kw.tech.search(title)), bool(kw.non_tech.search(title))
    if tech and non_tech:
        is_tech = None  # e.g. "Sales Operations & Data": let Gemini read the posting
    elif tech:
        is_tech = True
    elif non_tech:
        is_tech = False
    else:
        is_tech = None
    return Classification(is_internship, is_tech)
