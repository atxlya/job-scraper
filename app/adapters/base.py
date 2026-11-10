"""What every scraper adapter returns. See docs/DESIGN.md §3."""

from datetime import UTC, datetime
from typing import ClassVar, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, Field

from app.http.client import PoliteClient

Mode = Literal["incremental", "full"]


class RawJob(BaseModel):
    external_id: str
    title: str
    url: str
    apply_url: str | None = None
    locations: list[str] = Field(default_factory=list)
    country_codes: list[str] = Field(default_factory=list)
    remote_type: Literal["onsite", "hybrid", "remote"] | None = None
    employment_type: str | None = None
    posted_at: AwareDatetime | None = None
    description_html: str | None = None
    platform_flags: dict[str, bool] = Field(default_factory=dict)


class ListingResult(BaseModel):
    jobs: list[RawJob]
    reported_total: int | None
    complete: bool  # every page of every configured query was read (full mode)


class Gone:
    """Returned by fetch_detail when the job no longer exists on the site."""


GONE = Gone()


class ParseError(Exception):
    """The site's response did not have the shape the adapter expects."""


class Adapter(Protocol):
    name: ClassVar[str]

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult: ...

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone: ...


ADAPTERS: dict[str, type[Adapter]] = {}


def register[T](cls: type[T]) -> type[T]:
    name = cls.name  # type: ignore[attr-defined]
    if name in ADAPTERS:
        raise ValueError(f"adapter {name!r} already registered")
    ADAPTERS[name] = cls  # type: ignore[assignment]
    return cls


def utc(dt: datetime) -> datetime:
    """Attach UTC to naive datetimes; convert aware ones to UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
