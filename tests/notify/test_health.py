from datetime import UTC, datetime

import pytest

from app.core.db import make_engine, make_session_factory
from app.core.models import Base, Company, ScrapeRun, Source
from app.notify.health import _problem

T0 = datetime(2026, 11, 11, 2, 0, tzinfo=UTC)


@pytest.fixture
def session():
    eng = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as s:
        yield s


def _runs(session, config, counts=(2, 0)):
    c = Company(slug="z", name="Z")
    session.add(c)
    session.flush()
    src = Source(company_id=c.id, key="z", adapter="fake", config=config)
    session.add(src)
    session.flush()
    for found in counts:
        run = ScrapeRun(source_id=src.id, kind="full", status="ok", started_at=T0, jobs_found=found)
        session.add(run)
        session.flush()
    return src, run


def test_drop_warning_on_plain_source(session):
    src, run = _runs(session, {})
    assert "dropped from 2 to 0" in _problem(session, src, run)


def test_no_drop_warning_when_allow_empty(session):
    src, run = _runs(session, {"allow_empty": True})
    assert _problem(session, src, run) is None


def test_allow_empty_still_warns_on_a_drop_to_a_few(session):
    src, run = _runs(session, {"allow_empty": True}, counts=(40, 3))
    assert "dropped from 40 to 3" in _problem(session, src, run)
