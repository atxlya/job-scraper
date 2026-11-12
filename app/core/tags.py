"""Changing a job's tag. The dashboard (PUT /api/jobs/{id}/tag) and the Telegram buttons
both call set_tag, so a change looks the same in tag_history wherever it was made."""

from datetime import date, datetime

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.models import JobUserState, TagHistory


def user_state(s: Session, job_id: int) -> JobUserState:
    """The job's state row, created if missing. The caller checks the job exists."""
    # Insert-or-ignore, not get-then-add: "seen" and a tag change for a new job can arrive
    # at the same moment (keyboard triage), and both would try to create the row.
    s.execute(
        sqlite_insert(JobUserState)
        .values(job_id=job_id)
        .on_conflict_do_nothing(index_elements=["job_id"])
    )
    return s.get(JobUserState, job_id, populate_existing=True)


def set_tag(
    s: Session,
    job_id: int,
    tag: str | None,
    at: datetime,
    event_date: date | None = None,
    note: str | None = None,
) -> JobUserState:
    """Sets the tag (None removes it). A history row is added only when the tag changes."""
    us = user_state(s, job_id)
    if us.tag != tag:
        s.add(
            TagHistory(
                job_id=job_id, from_tag=us.tag, to_tag=tag, at=at, event_date=event_date, note=note
            )
        )
        us.tag = tag
    s.flush()
    return us
