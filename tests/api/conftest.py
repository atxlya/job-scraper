"""Shared fixtures for API tests: an app on a temp file DB, logged-in and anonymous clients."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import create_app
from app.core.db import make_engine
from app.core.models import Base, Company, Job, JobAnalysis, JobUserState, Source
from app.core.secrets import hash_password
from app.core.settings import Settings
from app.pipeline.derived import create_fts, refresh_derived

T0 = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
MIN, HOUR, DAY = timedelta(minutes=1), timedelta(hours=1), timedelta(days=1)
PASSWORD = "correct horse"
_HASH = hash_password(PASSWORD)  # argon2 is slow; hash once per test session


def make_settings(tmp_path, **kw) -> Settings:
    kw.setdefault("dashboard_password_hash", _HASH)
    return Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'jobs.db'}", **kw)


def make_app(tmp_path, **kw):
    s = make_settings(tmp_path, **kw)
    eng = make_engine(s.database_url)
    Base.metadata.create_all(eng)
    create_fts(eng)
    return create_app(s)


@pytest.fixture
def app(tmp_path):
    return make_app(tmp_path)


@pytest.fixture
def anon(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        assert c.post("/api/login", json={"password": PASSWORD}).status_code == 204
        yield c


@pytest.fixture
def db(app):
    with app.state.session_factory() as s:
        yield s


def _company(db, name: str, adapter: str) -> tuple[Company, Source]:
    slug = name.lower().replace(" ", "-")
    c = db.scalars(select(Company).where(Company.slug == slug)).first()
    if c is None:
        c = Company(slug=slug, name=name)
        db.add(c)
        db.flush()
        db.add(Source(company_id=c.id, key=slug, adapter=adapter, config={}))
        db.flush()
    src = db.scalars(select(Source).where(Source.company_id == c.id)).first()
    return c, src


def seed_job(
    db,
    company="Google",
    title="Software Engineering Intern",
    *,
    intern=True,
    tech=True,
    countries=("IN",),
    locations=None,
    remote=None,
    first_seen=T0,
    posted=None,
    state="open",
    analysis=None,
    quote=None,
    sections=None,
    tag=None,
    seen=False,
    description="<p>x</p>",
    adapter="fake-api",
) -> Job:
    c, src = _company(db, company, adapter)
    n = (db.scalar(select(Job.id).order_by(Job.id.desc())) or 0) + 1
    j = Job(
        company_id=c.id,
        source_ids=[src.id],
        external_id=f"ext-{n}",
        url=f"https://jobs.example/{n}",
        apply_url=f"https://jobs.example/{n}/apply",
        title=title,
        locations=list(locations) if locations is not None else ["Bengaluru, India"],
        country_codes=list(countries),
        remote_type=remote,
        posted_at=posted,
        description_html=description,
        content_hash="h",
        is_internship=intern,
        is_tech=tech,
        state=state,
        closed_at=first_seen if state == "closed" else None,
        first_seen_at=first_seen,
        last_seen_at=first_seen,
    )
    db.add(j)
    db.flush()
    if analysis is not None:
        db.add(
            JobAnalysis(
                job_id=j.id,
                model="m",
                prompt_version="2",
                sections=sections or {},
                eligibility=analysis,
                eligibility_quote=quote,
                created_at=first_seen,
            )
        )
        j.analysis_state = "done"
    if tag is not None or seen:
        db.add(JobUserState(job_id=j.id, tag=tag, seen_at=first_seen if seen else None))
    refresh_derived(db, [j.id])
    db.commit()
    return j


class FakeApiAdapter:
    """Adapter "fake-api": each test sets what it returns through the fake_adapter fixture."""

    name = "fake-api"
    state = None  # set by the fixture

    async def list_jobs(self, client, cfg, mode):
        FakeApiAdapter.state.calls += 1
        if isinstance(FakeApiAdapter.state.listing, Exception):
            raise FakeApiAdapter.state.listing
        return FakeApiAdapter.state.listing

    async def fetch_detail(self, client, cfg, job):
        FakeApiAdapter.state.calls += 1
        d = FakeApiAdapter.state.detail
        if isinstance(d, Exception):
            raise d
        return d if d is not None else job


class _FakeState:
    def __init__(self):
        self.calls = 0
        self.detail = None
        self.listing = None


@pytest.fixture
def fake_adapter():
    from app.adapters.base import ADAPTERS  # noqa: PLC0415

    FakeApiAdapter.state = _FakeState()
    ADAPTERS["fake-api"] = FakeApiAdapter
    yield FakeApiAdapter.state
    ADAPTERS.pop("fake-api", None)
