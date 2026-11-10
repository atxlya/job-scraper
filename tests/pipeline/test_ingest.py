from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.adapters.base import ListingResult, RawJob
from app.core.db import make_engine, make_session_factory
from app.core.models import Base, Company, Job, JobChange, Source
from app.pipeline.ingest import content_hash, ingest, mark_gone

T0 = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)


@pytest.fixture
def session():
    eng = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as s:
        yield s


@pytest.fixture
def setup(session):
    c = Company(slug="visa", name="Visa")
    session.add(c)
    session.flush()
    a = Source(company_id=c.id, key="visa-main", adapter="workday", config={})
    b = Source(company_id=c.id, key="visa-early", adapter="workday", config={})
    session.add_all([a, b])
    session.flush()
    return c, a, b


def raw(ext="JR1", title="Software Engineer Intern", desc="<p>Build things</p>", **kw):
    return RawJob(
        external_id=ext,
        title=title,
        url=f"https://x/{ext or 'nourl'}",
        description_html=desc,
        locations=["Bengaluru, India"],
        **kw,
    )


def res(*jobs, complete=True, total=None):
    return ListingResult(jobs=list(jobs), reported_total=total, complete=complete)


def jobs(session):
    return session.scalars(select(Job)).all()


def test_new_job_inserted(session, setup):
    _, a, _ = setup
    st = ingest(session, a, res(raw()), "incremental", T0)
    [j] = jobs(session)
    assert st.new_ids == [j.id]
    assert j.first_seen_at == T0 and j.state == "open" and j.source_ids == [a.id]


def test_same_job_twice_no_duplicate(session, setup):
    _, a, _ = setup
    ingest(session, a, res(raw()), "incremental", T0)
    st = ingest(session, a, res(raw()), "incremental", T0 + timedelta(minutes=30))
    [j] = jobs(session)
    assert st.new_ids == [] and j.last_seen_at == T0 + timedelta(minutes=30)


def test_same_job_two_sources_one_row(session, setup):
    _, a, b = setup
    st1 = ingest(session, a, res(raw()), "incremental", T0)
    st2 = ingest(session, b, res(raw()), "incremental", T0)
    [j] = jobs(session)
    assert len(st1.new_ids) == 1 and st2.new_ids == []
    assert sorted(j.source_ids) == sorted([a.id, b.id])


def test_fallback_key_url_then_title_location(session, setup):
    _, a, _ = setup
    no_id = RawJob(
        external_id="", title="Data Intern", url="https://x/data-intern", locations=["Pune"]
    )
    ingest(session, a, res(no_id), "incremental", T0)
    ingest(session, a, res(no_id), "incremental", T0)
    assert len(jobs(session)) == 1
    no_url = RawJob(external_id="", title="QA Intern", url="", locations=["Pune"])
    ingest(session, a, res(no_url), "incremental", T0)
    ingest(session, a, res(no_url), "incremental", T0)
    assert len(jobs(session)) == 2


def test_change_logs_fields(session, setup):
    _, a, _ = setup
    ingest(session, a, res(raw()), "incremental", T0)
    st = ingest(session, a, res(raw(desc="<p>Build other things</p>")), "incremental", T0)
    [j] = jobs(session)
    [ch] = session.scalars(select(JobChange)).all()
    assert st.updated_ids == [j.id] and ch.fields == ["description"]
    assert j.description_html == "<p>Build other things</p>"


def test_listing_without_description_keeps_existing(session, setup):
    _, a, _ = setup
    ingest(session, a, res(raw()), "incremental", T0)
    st = ingest(session, a, res(raw(desc=None)), "incremental", T0)
    [j] = jobs(session)
    assert j.description_html == "<p>Build things</p>" and st.updated_ids == []


def test_close_after_two_complete_sweeps(session, setup):
    _, a, _ = setup
    ingest(session, a, res(raw()), "full", T0)
    ingest(session, a, res(raw("JR2")), "full", T0 + timedelta(days=1))
    j = session.scalars(select(Job).where(Job.external_id == "JR1")).one()
    assert j.state == "open" and j.missed_sweeps == 1
    st = ingest(session, a, res(raw("JR2")), "full", T0 + timedelta(days=2))
    assert j.state == "closed" and j.closed_at == T0 + timedelta(days=2)
    assert st.closed_ids == [j.id]


def test_partial_result_never_closes(session, setup):
    _, a, _ = setup
    ingest(session, a, res(raw()), "full", T0)
    for d in (1, 2, 3):
        ingest(session, a, res(raw("JR2"), complete=False), "full", T0 + timedelta(days=d))
    j = session.scalars(select(Job).where(Job.external_id == "JR1")).one()
    assert j.state == "open" and j.missed_sweeps == 0


def test_empty_complete_listing_of_known_source_never_closes(session, setup):
    """A 200 with zero jobs from a source that had jobs is a broken page, not mass closure."""
    _, a, _ = setup
    ingest(session, a, res(raw()), "full", T0)
    for d in (1, 2):
        ingest(session, a, res(complete=True, total=0), "full", T0 + timedelta(days=d))
    assert jobs(session)[0].state == "open"


def test_incremental_never_closes(session, setup):
    _, a, _ = setup
    ingest(session, a, res(raw()), "full", T0)
    for d in (1, 2, 3):
        ingest(session, a, res(raw("JR2")), "incremental", T0 + timedelta(days=d))
    assert session.scalars(select(Job).where(Job.external_id == "JR1")).one().state == "open"


def test_two_source_job_closes_only_when_both_miss_twice(session, setup):
    _, a, b = setup
    ingest(session, a, res(raw()), "full", T0)
    ingest(session, b, res(raw()), "full", T0)
    for d in (1, 2):
        ingest(session, a, res(raw("JR2")), "full", T0 + timedelta(days=d))
    j = session.scalars(select(Job).where(Job.external_id == "JR1")).one()
    assert j.state == "open"  # still listed on source b
    for d in (1, 2):
        ingest(session, b, res(raw("JR3")), "full", T0 + timedelta(days=d))
    assert j.state == "closed"


def test_reappearing_job_reopens(session, setup):
    _, a, _ = setup
    ingest(session, a, res(raw()), "full", T0)
    [j] = jobs(session)
    mark_gone(session, j, T0)
    st = ingest(session, a, res(raw()), "incremental", T0 + timedelta(days=1))
    assert j.state == "open" and j.closed_at is None
    assert st.reopened_ids == [j.id] and st.new_ids == []


def test_mark_gone_closes_immediately(session, setup):
    _, a, _ = setup
    ingest(session, a, res(raw()), "incremental", T0)
    [j] = jobs(session)
    mark_gone(session, j, T0)
    assert j.state == "closed" and j.closed_at == T0


def test_content_hash_ignores_whitespace_and_location_order():
    h1 = content_hash(
        RawJob(
            external_id="1",
            title="A",
            url="u",
            description_html="<p>x  y</p>",
            locations=["B", "A"],
        )
    )
    h2 = content_hash(
        RawJob(
            external_id="1", title="A", url="u", description_html="<p>x y</p>", locations=["A", "B"]
        )
    )
    assert h1 == h2
