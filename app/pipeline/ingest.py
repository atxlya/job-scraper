"""Store a source's listing: insert new jobs, update changed ones, detect closed ones.

A job is closed when its detail page says it is gone (mark_gone), or when every
source that lists it has missed it in 2 consecutive complete full sweeps.
"""

import hashlib
import re
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import ListingResult, RawJob
from app.core.models import Job, JobChange, Source

CLOSE_AFTER_MISSES = 2

# RawJob field -> (Job column, name recorded in the change log)
TRACKED = {
    "title": ("title", "title"),
    "description_html": ("description_html", "description"),
    "locations": ("locations", "locations"),
    "apply_url": ("apply_url", "apply_url"),
    "employment_type": ("employment_type", "employment_type"),
    "posted_at": ("posted_at", "posted_at"),
}


class IngestStats(BaseModel):
    new_ids: list[int] = Field(default_factory=list)
    updated_ids: list[int] = Field(default_factory=list)
    closed_ids: list[int] = Field(default_factory=list)
    reopened_ids: list[int] = Field(default_factory=list)
    seen: int = 0


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def content_hash(raw: RawJob) -> str:
    parts = [_norm(raw.title), _norm(raw.description_html), "|".join(sorted(raw.locations))]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def job_key(raw: RawJob) -> str:
    """The unique key a job is stored under for its company."""
    if raw.external_id:
        return raw.external_id
    if raw.url:
        return "url:" + raw.url.split("#", 1)[0].rstrip("/")
    digest = hashlib.sha1(f"{_norm(raw.title)}|{'|'.join(sorted(raw.locations))}".encode())
    return "tl:" + digest.hexdigest()


def _merged(raw: RawJob, job: Job) -> RawJob:
    """Listing pages often lack details; never let an empty value wipe a stored one."""
    update = {}
    for field, (col, _) in TRACKED.items():
        if getattr(raw, field) in (None, "", []):
            update[field] = getattr(job, col)
    if raw.title_from_url and job.title:
        update["title"] = job.title  # a title guessed from the URL never replaces a stored one
    return raw.model_copy(update=update)


def _update_fields(session: Session, job: Job, raw: RawJob, now: datetime) -> list[str]:
    """Copy changed tracked fields onto a stored job and log the change. Returns their names."""
    merged = _merged(raw, job)
    changed = [
        name
        for field, (col, name) in TRACKED.items()
        if getattr(merged, field) != getattr(job, col)
    ]
    if changed:
        if not job.description_html and merged.description_html:
            # Gemini skipped it for lack of text; now there is some to read.
            if job.analysis_state == "skipped":
                job.analysis_state = "pending"
        for field, (col, _) in TRACKED.items():
            setattr(job, col, getattr(merged, field))
        job.content_hash = content_hash(merged)
        session.add(JobChange(job_id=job.id, changed_at=now, fields=changed))
    return changed


def raw_from_job(job: Job) -> RawJob:
    """What an adapter needs to fetch a stored job's detail page again."""
    return RawJob(
        external_id=job.external_id,
        title=job.title,
        url=job.url,
        apply_url=job.apply_url,
        locations=job.locations or [],
        platform_flags=job.platform_flags or {},
    )


def apply_detail(session: Session, job: Job, raw: RawJob, now: datetime) -> list[str]:
    """Store a detail page fetched outside a scrape run (the dashboard's on-demand fetch)."""
    from app.pipeline.derived import refresh_derived  # noqa: PLC0415 - avoids an import cycle

    changed = _update_fields(session, job, raw, now)
    if changed:
        refresh_derived(session, [job.id])
    session.flush()
    return changed


def ingest(
    session: Session, source: Source, result: ListingResult, mode: str, now: datetime
) -> IngestStats:
    stats = IngestStats(seen=len(result.jobs))
    sid = str(source.id)
    seen_ids: set[int] = set()

    for raw in result.jobs:
        key = job_key(raw)
        job = session.scalars(
            select(Job).where(Job.company_id == source.company_id, Job.external_id == key)
        ).one_or_none()
        if job is None:
            job = _new_job(source, raw, key, now)
            session.add(job)
            session.flush()
            stats.new_ids.append(job.id)
            seen_ids.add(job.id)
            continue

        seen_ids.add(job.id)
        job.last_seen_at = now
        if source.id not in job.source_ids:
            job.source_ids = [*job.source_ids, source.id]
        misses = dict(job.missed_by_source or {})
        if misses.pop(sid, None) is not None:
            job.missed_by_source = misses
            job.missed_sweeps = min(misses.values(), default=0)
        if job.state == "closed":
            job.state, job.closed_at = "open", None
            stats.reopened_ids.append(job.id)

        if _update_fields(session, job, raw, now):
            stats.updated_ids.append(job.id)

    if mode == "full" and result.complete:
        stats.closed_ids = _close_missing(session, source, seen_ids, result, now)
    session.flush()
    return stats


def _new_job(source: Source, raw: RawJob, key: str, now: datetime) -> Job:
    return Job(
        company_id=source.company_id,
        source_ids=[source.id],
        external_id=key,
        url=raw.url,
        apply_url=raw.apply_url,
        title=raw.title,
        locations=raw.locations,
        country_codes=raw.country_codes,
        remote_type=raw.remote_type,
        employment_type=raw.employment_type,
        posted_at=raw.posted_at,
        description_html=raw.description_html,
        platform_flags=raw.platform_flags,
        content_hash=content_hash(raw),
        state="open",
        missed_sweeps=0,
        missed_by_source={},
        first_seen_at=now,
        last_seen_at=now,
    )


def _close_missing(
    session: Session, source: Source, seen_ids: set[int], result: ListingResult, now: datetime
) -> list[int]:
    open_jobs = [
        j
        for j in session.scalars(
            select(Job).where(Job.company_id == source.company_id, Job.state == "open")
        )
        if source.id in j.source_ids
    ]
    if not result.jobs and open_jobs and not (source.config or {}).get("allow_empty"):
        return []  # an empty "complete" listing is a broken page, not every job closing
    closed = []
    sid = str(source.id)
    for job in open_jobs:
        if job.id in seen_ids:
            continue
        misses = dict(job.missed_by_source or {})
        misses[sid] = misses.get(sid, 0) + 1
        job.missed_by_source = misses
        listed_by = [str(s) for s in job.source_ids]
        job.missed_sweeps = min(misses.get(s, 0) for s in listed_by)
        if job.missed_sweeps >= CLOSE_AFTER_MISSES:
            job.state, job.closed_at = "closed", now
            closed.append(job.id)
    return closed


def mark_gone(session: Session, job: Job, now: datetime) -> None:
    job.state, job.closed_at = "closed", now
    session.flush()
