"""One tag-change function, used by the dashboard's PUT /api/jobs/{id}/tag and the
Telegram buttons."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.core.db import make_engine, make_session_factory
from app.core.models import Base, Company, Job, JobUserState, TagHistory
from app.core.tags import set_tag

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
