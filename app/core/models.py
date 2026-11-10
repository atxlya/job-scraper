"""Database tables. See docs/DESIGN.md §4."""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UTCDateTime(TypeDecorator):
    """Stores UTC; always returns timezone-aware datetimes (SQLite drops tzinfo)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTCDateTime, dict[str, Any]: JSON, list: JSON}


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    supported: Mapped[bool] = mapped_column(Boolean, default=True)
    unsupported_reason: Mapped[str | None] = mapped_column(Text)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    key: Mapped[str] = mapped_column(String(120), unique=True)
    adapter: Mapped[str] = mapped_column(String(60))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    initial_load_done: Mapped[bool] = mapped_column(Boolean, default=False)
    last_success_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_job_count: Mapped[int | None]
    last_warned_at: Mapped[datetime | None]
    warning_active: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("company_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    external_id: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    apply_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    locations: Mapped[list] = mapped_column(JSON, default=list)
    country_codes: Mapped[list] = mapped_column(JSON, default=list)
    remote_type: Mapped[str | None] = mapped_column(String(20))
    employment_type: Mapped[str | None] = mapped_column(String(80))
    posted_at: Mapped[datetime | None]
    description_html: Mapped[str | None] = mapped_column(Text)
    platform_flags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    is_internship: Mapped[bool | None] = mapped_column(Boolean)
    is_tech: Mapped[bool | None] = mapped_column(Boolean)
    analysis_state: Mapped[str] = mapped_column(String(20), default="pending")
    state: Mapped[str] = mapped_column(String(10), default="open", index=True)
    missed_sweeps: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(index=True)
    last_seen_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]


class JobChange(Base):
    __tablename__ = "job_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    changed_at: Mapped[datetime]
    fields: Mapped[list] = mapped_column(JSON)


class JobAnalysis(Base):
    __tablename__ = "job_analysis"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(20))
    sections: Mapped[dict[str, Any]] = mapped_column(JSON)
    eligibility: Mapped[str] = mapped_column(String(10))  # ok | warn | unknown
    eligibility_quote: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]


class JobUserState(Base):
    __tablename__ = "job_user_state"
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), primary_key=True)
    seen_at: Mapped[datetime | None]
    tag: Mapped[str | None] = mapped_column(String(20))  # liked | applied | dismissed
    note: Mapped[str | None] = mapped_column(Text)


class TagHistory(Base):
    __tablename__ = "tag_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    from_tag: Mapped[str | None] = mapped_column(String(20))
    to_tag: Mapped[str | None] = mapped_column(String(20))
    at: Mapped[datetime]
    event_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    message_id: Mapped[int | None]
    grouped: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime]
    edited_at: Mapped[datetime | None]


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # incremental | full | tracked
    status: Mapped[str] = mapped_column(String(10))  # ok | failed | partial
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    reported_total: Mapped[int | None]
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    closed_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    day: Mapped[date] = mapped_column(Date, primary_key=True)  # Pacific-time date
    requests: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    effective_cap: Mapped[int | None]


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
