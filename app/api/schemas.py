"""Request and response shapes for the dashboard API (mirrored in web/src/types.ts)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

EligStatus = Literal["ok", "warn", "pending"]
Tag = Literal["liked", "applied", "dismissed"]
Stage = Literal["oa", "interview", "offer", "rejected"]  # after Applied (app/core/tags.py)


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
    place: str  # "City, Country" of the first location
    country: str | None  # its ISO code, for the flag
    more_places: int
    india: bool
    remote: bool
    posted_at: datetime | None
    first_seen_at: datetime
    is_new: bool
    eligibility: EligStatus
    tag: Tag | None
    stage: Stage | None  # only while tag is "applied"
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
    from_stage: str | None  # a stage step has from_tag = to_tag = "applied"
    to_stage: str | None
    event_date: date | None
    note: str | None


class Step(BaseModel):
    """One step of the current application: Applied, then each stage it moved to."""

    stage: Literal["applied", "oa", "interview", "offer", "rejected"]
    on: date
    at: datetime
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
    steps: list[Step]  # the current application, oldest first; empty unless applied


class Application(BaseModel):
    id: int
    company: str
    company_slug: str
    title: str
    closed: bool
    stage: Stage | None
    steps: list[Step]  # oldest first
    last_on: date  # the latest step's date: "how long since"


class TagBody(BaseModel):
    tag: Tag | None
    event_date: date | None = None
    note: str | None = Field(None, max_length=2000)


class StageBody(BaseModel):
    stage: Stage | None  # None: back to "just applied"
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


class LastRun(BaseModel):
    kind: str
    status: str
    started_at: datetime
    duration_s: int | None


class Night(BaseModel):
    day: str  # IST date of the nightly full sweep
    count: int | None  # jobs it read; None when there was no full run that night
    status: str | None  # ok | partial | failed


class SourceHealth(BaseModel):
    key: str
    company: str
    adapter: str
    origin: str
    enabled: bool
    # failing: failed runs in a row; partial: last run partial; warning: job count dropped
    status: Literal["failing", "partial", "warning", "ok", "never_run"]
    last_success_at: datetime | None
    last_job_count: int | None
    last_error: str | None
    consecutive_failures: int
    last_run: LastRun | None
    nights: list[Night]


class RunOut(LastRun):
    jobs_found: int
    reported_total: int | None
    new_count: int
    updated_count: int
    closed_count: int
    error: str | None


HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class ScheduleBody(BaseModel):
    incremental_minutes: int
    full_at: str = Field(pattern=HHMM)  # IST, "02:00"
    tracked_at: str = Field(pattern=HHMM)


class Schedule(ScheduleBody):
    next_full_at: datetime
    next_tracked_at: datetime


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
