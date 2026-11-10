import threading
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.db import make_engine, make_session_factory
from app.core.models import Alert, Base, Company, Job, Source


@pytest.fixture
def engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with make_session_factory(engine)() as s:
        yield s


def _company_source(session):
    c = Company(slug="visa", name="Visa")
    session.add(c)
    session.flush()
    src = Source(company_id=c.id, key="visa-main", adapter="workday", config={})
    session.add(src)
    session.flush()
    return c, src


def _job(c, src, ext="JR1"):
    now = datetime.now(UTC)
    return Job(
        company_id=c.id,
        external_id=ext,
        url="https://x/1",
        title="Intern",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h",
        source_ids=[src.id],
    )


def test_wal_and_busy_timeout(engine):
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_job_unique_per_company(session):
    c, src = _company_source(session)
    session.add(_job(c, src))
    session.flush()
    session.add(_job(c, src))
    with pytest.raises(IntegrityError):
        session.flush()


def test_alert_unique_per_job(session):
    c, src = _company_source(session)
    j = _job(c, src)
    session.add(j)
    session.flush()
    now = datetime.now(UTC)
    session.add(Alert(job_id=j.id, sent_at=now))
    session.flush()
    session.add(Alert(job_id=j.id, sent_at=now))
    with pytest.raises(IntegrityError):
        session.flush()


def test_concurrent_read_during_write(engine):
    sf = make_session_factory(engine)
    with sf() as s:
        c, src = _company_source(s)
        s.commit()
    started = threading.Event()
    errors: list[Exception] = []

    def writer():
        with sf() as s:
            s.add(_job(c, src, "W1"))
            s.flush()
            started.set()
            time.sleep(1)
            s.commit()

    def reader():
        started.wait()
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT count(*) FROM jobs")).scalar()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1, t2 = threading.Thread(target=writer), threading.Thread(target=reader)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert errors == []
