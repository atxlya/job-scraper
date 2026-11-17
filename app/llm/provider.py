"""What the LLM returns, and the guard against invented eligibility quotes."""

import re
from typing import Literal, Protocol

from pydantic import BaseModel

from app.core.categories import Category


class Sections(BaseModel):
    about: str
    responsibilities: list[str]
    requirements: list[str]
    preferred: list[str]
    eligibility: list[str]


class Analysis(BaseModel):
    sections: Sections
    is_internship: bool
    is_tech: bool
    category: Category
    eligibility: Literal["ok", "warn", "unknown"]
    eligibility_quote: str | None = None


class RateLimited(Exception):
    """The provider answered 429 / quota exceeded."""


class Busy(Exception):
    """The provider is overloaded or briefly down (5xx). Not our quota: try again later."""


class LlmProvider(Protocol):
    async def analyze(self, title: str, text: str) -> Analysis: ...

    async def classify_titles(self, titles: list[str]) -> list[tuple[bool, bool]]: ...

    async def categorize_titles(self, jobs: list[tuple[str, str]]) -> list[Category]: ...


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def validate_quotes(a: Analysis, source_text: str) -> Analysis:
    """A quote that does not appear in the posting is discarded; eligibility becomes unknown."""
    if a.eligibility_quote and _squash(a.eligibility_quote) not in _squash(source_text):
        return a.model_copy(update={"eligibility": "unknown", "eligibility_quote": None})
    if a.eligibility == "warn" and not a.eligibility_quote:
        return a.model_copy(update={"eligibility": "unknown"})
    return a
