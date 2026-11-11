from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from app.core.db import make_engine, make_session_factory
from app.core.models import Base, Company, Job, Source
from app.core.registry import CompanySpec, SourceSpec, sync_registry
from app.pipeline.derived import create_fts, fts_query, refresh_derived

T0 = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)


@pytest.fixture
def session():
    eng = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    create_fts(eng)
    with make_session_factory(eng)() as s:
        yield s


def add_job(session, title="Software Intern", desc="<p>x</p>", ext=None):
    company = session.scalars(select(Company)).first()
    if company is None:
        company = Company(slug="google", name="Google")
        session.add(company)
        session.flush()
    j = Job(
        company_id=company.id,
        external_id=ext or f"e{session.scalar(select(Job.id).order_by(Job.id.desc())) or 0}",
        url="https://x",
        title=title,
        description_html=desc,
        content_hash="h",
        first_seen_at=T0,
        last_seen_at=T0,
    )
    session.add(j)
    session.flush()
    return j


def search_ids(session, q):
    m = fts_query(q)
    if m is None:
        return []
    rows = session.execute(text("SELECT rowid FROM jobs_fts WHERE jobs_fts MATCH :q"), {"q": m})
    return [r[0] for r in rows]


def test_refresh_sets_degree_and_search_row(session):
    j = add_job(
        session, title="Software Engineering PhD Intern", desc="<p>Build <b>compilers</b></p>"
    )
    refresh_derived(session, [j.id])
    assert j.degree_only == "PhD"
    assert search_ids(session, "compilers") == [j.id]
    assert search_ids(session, "google") == [j.id]


def test_refresh_replaces_old_row(session):
    j = add_job(session, title="Data Intern", desc="<p>old words</p>")
    refresh_derived(session, [j.id])
    j.description_html = "<p>new words</p>"
    refresh_derived(session, [j.id])
    assert search_ids(session, "old") == []
    assert search_ids(session, "new") == [j.id]


def test_refresh_clears_degree_when_title_changes(session):
    j = add_job(session, title="PhD Intern")
    refresh_derived(session, [j.id])
    j.title = "Software Intern"
    refresh_derived(session, [j.id])
    assert j.degree_only is None


@pytest.mark.parametrize("q", ['"', "-", "*", "AND", "NEAR(", "(", "c++", "a OR", "'; drop"])
def test_fts_query_never_raises(session, q):
    j = add_job(session, title="C++ Intern")
    refresh_derived(session, [j.id])
    search_ids(session, q)


def test_fts_query_prefix_matches_words():
    assert fts_query("soft eng") == '"soft"* "eng"*'
    assert fts_query('  "  ') is None


def test_registry_sync_keeps_dashboard_sources(session):
    c = Company(slug="acme", name="Acme")
    session.add(c)
    session.flush()
    session.add(Source(company_id=c.id, key="acme", adapter="workday", origin="dashboard"))
    session.flush()
    sync_registry(
        session,
        [CompanySpec(slug="v", name="V", sources=[SourceSpec(key="v1", adapter="workday")])],
    )
    acme = session.scalars(select(Source).where(Source.key == "acme")).one()
    assert acme.enabled is True


def test_unindexed_ids_lists_only_jobs_missing_from_the_index(session):
    from app.pipeline.derived import unindexed_ids  # noqa: PLC0415

    a, b = add_job(session, ext="a"), add_job(session, ext="b")
    assert unindexed_ids(session) == [a.id, b.id]
    refresh_derived(session, [a.id])
    assert unindexed_ids(session) == [b.id]
