"""Changing a job's tag and, once it's Applied, its stage. The dashboard (PUT
/api/jobs/{id}/tag and /stage) and the Telegram buttons call these, so a change looks the
same in tag_history wherever it was made.

A stage (OA, interview, offer, rejected) sits next to the tag: an applied job keeps the
tag "applied" whatever its stage, so every rule about applied jobs (never hidden, counted
in the stats, re-checked daily, "closed" messages) holds for it. Each stage step is a
tag_history row with from_tag = to_tag = "applied" and the stages it moved between.
"""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.models import JobUserState, TagHistory

IST = ZoneInfo("Asia/Kolkata")
STAGES = ("oa", "interview", "offer", "rejected")
STAGE_LABEL = {"oa": "OA", "interview": "Interview", "offer": "Offer", "rejected": "Rejected"}


class NotApplied(ValueError):
    """A stage was set on a job that isn't tagged Applied."""


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
    """Sets the tag (None removes it). A history row is added only when the tag changes.
    Leaving "applied" clears the stage; the history row records which stage it was."""
    us = user_state(s, job_id)
    if us.tag != tag:
        s.add(
            TagHistory(
                job_id=job_id,
                from_tag=us.tag,
                to_tag=tag,
                from_stage=us.stage,
                at=at,
                event_date=event_date,
                note=note,
            )
        )
        us.tag, us.stage = tag, None
    s.flush()
    return us


def set_stage(
    s: Session,
    job_id: int,
    stage: str | None,
    at: datetime,
    event_date: date | None = None,
    note: str | None = None,
) -> JobUserState:
    """Moves an applied job to a stage (None: back to "just applied")."""
    us = user_state(s, job_id)
    if us.tag != "applied":
        raise NotApplied(job_id)
    if us.stage != stage:
        s.add(
            TagHistory(
                job_id=job_id,
                from_tag="applied",
                to_tag="applied",
                from_stage=us.stage,
                to_stage=stage,
                at=at,
                event_date=event_date,
                note=note,
            )
        )
        us.stage = stage
    s.flush()
    return us


@dataclass
class Step:
    stage: str  # "applied", or one of STAGES
    on: date  # the date given, else the day it was recorded (IST)
    at: datetime
    note: str | None


def _is_step(h: TagHistory) -> bool:
    return h.from_tag == "applied" and h.to_tag == "applied"


def application_steps(history: list[TagHistory]) -> list[Step]:
    """The current application's steps, oldest first: from the latest move into Applied.
    Empty when the job isn't Applied now. `history` is one job's rows, in id order."""
    rows = sorted(history, key=lambda h: h.id)
    if not rows or rows[-1].to_tag != "applied":
        return []
    start = max(
        (i for i, h in enumerate(rows) if h.to_tag == "applied" and not _is_step(h)), default=None
    )
    picked = rows[start:] if start is not None else [h for h in rows if _is_step(h)]
    return [
        Step(
            stage=(h.to_stage or "applied") if _is_step(h) else "applied",
            on=h.event_date or h.at.astimezone(IST).date(),
            at=h.at,
            note=h.note,
        )
        for h in picked
    ]
