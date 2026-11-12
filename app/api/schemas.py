"""Request and response shapes for the dashboard API (mirrored in web/src/types.ts)."""

from datetime import date, datetime
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
    new: Literal["today"] | None = None  # first seen since midnight IST, like the stats tile
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
    max_id: int  # newest committed job when the list loaded; "Mark all as seen" stops here (D7)


class Option(BaseModel):
    value: str
    label: str
    count: int


class FilterOptions(BaseModel):
    companies: list[Option]
    countries: list[Option]


class Change(BaseModel):
    at: datetime
    fields: list[str]


class TagEvent(BaseModel):
    at: datetime
    from_tag: str | None
    to_tag: str | None
    event_date: date | None
    note: str | None


class JobDetail(JobCard):
    external_id: str
    locations: list[str]
    employment_type: str | None
    remote_type: str | None
    url: str
    apply_url: str | None
    degree: str | None
    quote: str | None
    checking: bool
    unclear: bool
    unchecked: Literal["notice", "partial", "snippet"] | None  # why Gemini never reads it
    tech_internship: bool  # eligibility is only checked for these
    sections: dict | None
    description_html: str | None  # sanitised; only when there are no sections
    has_description: bool
    note: str | None
    changes: list[Change]  # oldest first
    tag_history: list[TagEvent]  # oldest first


class TagBody(BaseModel):
    tag: Tag | None
    event_date: date | None = None
    note: str | None = Field(None, max_length=2000)


class NoteBody(BaseModel):
    note: str = Field(max_length=5000)


class MarkSeenBody(BaseModel):
    # A job number, not a time: the worker stamps first_seen_at before it commits, so a
    # time cut-off could mark jobs that weren't on screen yet. SQLite has one writer, so
    # anything committed after the list loaded has a larger id.
    up_to_id: int = Field(ge=0)


class Stats(BaseModel):
    new_today: int
    open_tech: int
    companies: int
    liked: int
    applied: int
    last_applied_at: datetime | None


class SourceHealth(BaseModel):
    key: str
    company: str
    adapter: str
    origin: str
    enabled: bool
    status: Literal["ok", "failing", "never_run"]
    last_success_at: datetime | None
    last_job_count: int | None
    last_error: str | None
    consecutive_failures: int


class UrlBody(BaseModel):
    url: str = Field(max_length=2000)


class DetectedOut(BaseModel):
    adapter: str
    config: dict
    key_hint: str


class AddCompany(BaseModel):
    company_name: str = Field(min_length=1, max_length=120)
    url: str = Field(max_length=2000)


class AddResult(BaseModel):
    key: str
    jobs_found: int
    sample_titles: list[str]
