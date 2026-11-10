"""Request and response shapes for the dashboard API (mirrored in web/src/types.ts)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EligStatus = Literal["ok", "warn", "pending"]
Tag = Literal["liked", "applied", "dismissed"]


class JobFilters(BaseModel):
    view: Literal["tech", "all"] = "tech"
    company: list[str] = Field(default_factory=list)
    loc: str = Field("anywhere", pattern=r"^(anywhere|india|[A-Z]{2})$")
    elig: list[EligStatus] = Field(default_factory=list)
    posted: Literal["1d", "7d", "30d", "any"] = "any"
    tag: list[Literal["liked", "applied", "untagged"]] = Field(default_factory=list)
    dismissed: bool = False
    q: str | None = None


class JobCard(BaseModel):
    id: int
    company: str
    company_slug: str
    title: str
    location: str
    posted_at: datetime | None
    first_seen_at: datetime
    is_new: bool
    eligibility: EligStatus
    tag: Tag | None
    closed: bool


class JobPage(BaseModel):
    total: int
    items: list[JobCard]
    loaded_at: datetime


class Option(BaseModel):
    value: str
    label: str
    count: int


class FilterOptions(BaseModel):
    companies: list[Option]
    countries: list[Option]
