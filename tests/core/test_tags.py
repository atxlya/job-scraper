"""One tag-change function, used by the dashboard's PUT /api/jobs/{id}/tag and the
Telegram buttons."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.core.db import make_engine, make_session_factory
from app.core.models import Base, Company, Job, JobUserState, TagHistory
from app.core.tags import NotApplied, application_steps, set_stage, set_tag

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)


@pytest.fixture
def session():
    eng = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as s:
        yield s


def job(session):
    c = Company(slug="g", name="G")
    session.add(c)
    session.flush()
    j = Job(
        company_id=c.id,
        external_id="1",
        url="https://x/1",
        title="SWE Intern",
        content_hash="h",
        first_seen_at=T0,
        last_seen_at=T0,
    )
    session.add(j)
    session.flush()
    return j


def history(session, job_id):
    return [
        (h.from_tag, h.to_tag, h.event_date, h.note)
        for h in session.scalars(select(TagHistory).where(TagHistory.job_id == job_id))
    ]


def test_creates_the_state_row_and_records_history(session):
    j = job(session)
    us = set_tag(session, j.id, "applied", T0, event_date=date(2026, 11, 12), note="referral")
    assert us.tag == "applied" and session.get(JobUserState, j.id).tag == "applied"
    assert history(session, j.id) == [(None, "applied", date(2026, 11, 12), "referral")]


def test_same_tag_twice_records_nothing_new(session):
    j = job(session)
    set_tag(session, j.id, "liked", T0)
    set_tag(session, j.id, "liked", T0)
    set_tag(session, j.id, None, T0)
    assert [h[:2] for h in history(session, j.id)] == [(None, "liked"), ("liked", None)]


def test_keeps_seen_and_note(session):
    j = job(session)
    session.add(JobUserState(job_id=j.id, seen_at=T0, note="n"))
    session.flush()
    us = set_tag(session, j.id, "dismissed", T0)
    assert (us.seen_at, us.note, us.tag) == (T0, "n", "dismissed")


# --- stages after Applied ---------------------------------------------------------------

LATER = datetime(2026, 11, 15, 8, 0, tzinfo=UTC)


def stage_history(session, job_id):
    return [
        (h.from_tag, h.to_tag, h.from_stage, h.to_stage)
        for h in session.scalars(select(TagHistory).where(TagHistory.job_id == job_id))
    ]


def test_stage_needs_applied(session):
    j = job(session)
    with pytest.raises(NotApplied):
        set_stage(session, j.id, "oa", T0)
    set_tag(session, j.id, "liked", T0)
    with pytest.raises(NotApplied):
        set_stage(session, j.id, "oa", T0)


def test_stage_steps_are_history_rows_and_keep_the_tag(session):
    j = job(session)
    set_tag(session, j.id, "applied", T0, event_date=date(2026, 11, 3))
    set_stage(session, j.id, "oa", T0, event_date=date(2026, 11, 8), note="HackerRank")
    us = set_stage(session, j.id, "interview", LATER)
    set_stage(session, j.id, "interview", LATER)  # same stage: nothing new
    assert (us.tag, us.stage) == ("applied", "interview")
    assert stage_history(session, j.id) == [
        (None, "applied", None, None),
        ("applied", "applied", None, "oa"),
        ("applied", "applied", "oa", "interview"),
    ]


def test_leaving_applied_clears_the_stage_but_history_keeps_it(session):
    j = job(session)
    set_tag(session, j.id, "applied", T0)
    set_stage(session, j.id, "rejected", T0)
    us = set_tag(session, j.id, "liked", LATER)
    assert (us.tag, us.stage) == ("liked", None)
    assert stage_history(session, j.id)[-1] == ("applied", "liked", "rejected", None)


def test_applied_again_on_an_applied_job_keeps_the_stage(session):
    j = job(session)
    set_tag(session, j.id, "applied", T0)
    set_stage(session, j.id, "offer", T0)
    assert set_tag(session, j.id, "applied", LATER).stage == "offer"


def test_steps_start_at_the_latest_apply(session):
    j = job(session)
    set_tag(session, j.id, "applied", T0, event_date=date(2026, 11, 1))
    set_stage(session, j.id, "rejected", T0)
    set_tag(session, j.id, None, T0)
    set_tag(session, j.id, "applied", LATER, event_date=date(2026, 11, 14), note="re-applied")
    set_stage(session, j.id, "oa", LATER, note="CodeSignal")
    rows = list(session.scalars(select(TagHistory).where(TagHistory.job_id == j.id)))
    assert [(s.stage, s.on, s.note) for s in application_steps(rows)] == [
        ("applied", date(2026, 11, 14), "re-applied"),
        ("oa", date(2026, 11, 15), "CodeSignal"),  # no date given: the day it was set, IST
    ]


def test_steps_for_a_job_not_applied_are_empty(session):
    j = job(session)
    set_tag(session, j.id, "applied", T0)
    set_tag(session, j.id, "dismissed", T0)
    rows = list(session.scalars(select(TagHistory).where(TagHistory.job_id == j.id)))
    assert application_steps(rows) == []
