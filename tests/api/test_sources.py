from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.adapters.base import ListingResult, RawJob
from app.api.deps import now
from app.core.models import Company, Source
from app.core.registry import CompanySpec, SourceSpec, sync_registry
from app.sources.detect import Detected

from .conftest import DAY, HOUR, seed_job

# 10:00 IST on 11 Nov = 04:30 UTC
NOW = datetime(2026, 11, 11, 4, 30, tzinfo=UTC)


def test_stats_counts(client, app, db):
    app.dependency_overrides[now] = lambda: NOW
    seed_job(db, first_seen=NOW - HOUR)  # 09:00 IST today
    seed_job(db, first_seen=NOW - DAY)  # yesterday
    seed_job(db, title="HR Intern", tech=False, first_seen=NOW - HOUR)  # not tech
    seed_job(db, company="NVIDIA", tag="liked", first_seen=NOW - DAY)
    j = seed_job(db, company="NVIDIA", first_seen=NOW - DAY)
    client.put(f"/api/jobs/{j.id}/tag", json={"tag": "applied"})
    st = client.get("/api/stats").json()
    assert st == {
        "new_today": 1,
        "open_tech": 4,
        "companies": 2,
        "liked": 1,
        "applied": 1,
        "last_applied_at": "2026-11-11T04:30:00Z",
    }


def test_sources_failing_first(client, db):
    seed_job(db, company="Alpha")
    seed_job(db, company="Beta")
    seed_job(db, company="Gamma")
    srcs = {s.key: s for s in db.scalars(select(Source))}
    srcs["alpha"].last_success_at = NOW
    srcs["alpha"].last_job_count = 40
    srcs["beta"].last_success_at = NOW - DAY
    srcs["beta"].consecutive_failures = 2
    srcs["beta"].last_error = "ParseError: site changed"
    db.commit()
    rows = client.get("/api/sources").json()
    assert [(r["key"], r["status"]) for r in rows] == [
        ("beta", "failing"),
        ("alpha", "ok"),
        ("gamma", "never_run"),
    ]
    assert rows[0]["last_error"] == "ParseError: site changed" and rows[0]["company"] == "Beta"


@pytest.fixture
def detected(monkeypatch):
    monkeypatch.setattr(
        "app.sources.detect.detect",
        lambda url: (
            Detected("fake-api", {"host": "acme.example"}, "acme") if "acme" in url else None
        ),
    )


def listing(n):
    return ListingResult(
        jobs=[
            RawJob(external_id=str(i), title=f"Job {i}", url=f"https://acme/{i}") for i in range(n)
        ],
        reported_total=n,
        complete=False,
    )


def test_detect_route(client, detected):
    r = client.post("/api/sources/detect", json={"url": "https://acme.example/jobs"})
    assert r.json() == {
        "adapter": "fake-api",
        "config": {"host": "acme.example"},
        "key_hint": "acme",
    }
    r = client.post("/api/sources/detect", json={"url": "https://nope.example"})
    assert r.status_code == 422 and "Workday" in r.json()["detail"]


def test_add_company_saves_only_after_good_test_fetch(client, db, detected, fake_adapter):
    fake_adapter.listing = listing(7)
    r = client.post(
        "/api/sources", json={"company_name": "Acme Corp", "url": "https://acme.example"}
    )
    assert r.status_code == 201
    assert r.json() == {
        "key": "acme-corp",
        "jobs_found": 7,
        "sample_titles": ["Job 0", "Job 1", "Job 2", "Job 3", "Job 4"],
    }
    src = db.scalars(select(Source).where(Source.key == "acme-corp")).one()
    assert (src.origin, src.enabled, src.adapter) == ("dashboard", True, "fake-api")
    assert db.scalars(select(Company).where(Company.slug == "acme-corp")).one().name == "Acme Corp"


def test_add_company_bad_fetch_saves_nothing(client, db, detected, fake_adapter):
    fake_adapter.listing = listing(0)
    r = client.post("/api/sources", json={"company_name": "Acme", "url": "https://acme.example"})
    assert r.status_code == 422 and "0 jobs" in r.json()["detail"]
    fake_adapter.listing = RuntimeError("boom")
    r = client.post("/api/sources", json={"company_name": "Acme", "url": "https://acme.example"})
    assert r.status_code == 422 and "boom" in r.json()["detail"]
    assert db.scalars(select(Source)).all() == []


def test_add_company_unknown_url_422(client, detected):
    r = client.post("/api/sources", json={"company_name": "X", "url": "https://nope.example"})
    assert r.status_code == 422


def test_add_company_existing_key_409(client, db, detected, fake_adapter):
    fake_adapter.listing = listing(3)
    seed_job(db, company="Acme")
    r = client.post("/api/sources", json={"company_name": "Acme", "url": "https://acme.example"})
    assert r.status_code == 409 and fake_adapter.calls == 0


def test_added_source_survives_registry_sync(client, db, detected, fake_adapter):
    fake_adapter.listing = listing(3)
    client.post("/api/sources", json={"company_name": "Acme", "url": "https://acme.example"})
    sync_registry(
        db, [CompanySpec(slug="v", name="V", sources=[SourceSpec(key="v", adapter="workday")])]
    )
    db.commit()
    assert db.scalars(select(Source).where(Source.key == "acme")).one().enabled is True


def test_same_site_under_another_name_409(client, db, detected, fake_adapter):
    fake_adapter.listing = listing(3)
    assert (
        client.post(
            "/api/sources", json={"company_name": "Acme", "url": "https://acme.example"}
        ).status_code
        == 201
    )
    r = client.post(
        "/api/sources", json={"company_name": "Acme India", "url": "https://acme.example/jobs"}
    )
    assert r.status_code == 409 and "acme" in r.json()["detail"]
    assert len(db.scalars(select(Source)).all()) == 1


def test_second_save_racing_the_first_is_409_not_500(client, app, db, detected, fake_adapter):
    from app.adapters.base import ADAPTERS  # noqa: PLC0415

    class Racing:
        name = "fake-api"

        async def list_jobs(self, c, cfg, mode):
            # the other click's save lands while this one is test-fetching
            with app.state.session_factory() as s:
                co = Company(slug="acme", name="Acme")
                s.add(co)
                s.flush()
                s.add(Source(company_id=co.id, key="acme", adapter="other", config={}))
                s.commit()
            return listing(3)

    ADAPTERS["fake-api"] = Racing
    r = client.post("/api/sources", json={"company_name": "Acme", "url": "https://acme.example"})
    assert r.status_code == 409


def test_same_site_with_extra_registry_keys_is_still_a_duplicate(
    client, db, detected, fake_adapter
):
    c = Company(slug="acme-reg", name="Acme")
    db.add(c)
    db.flush()
    db.add(
        Source(
            company_id=c.id,
            key="acme-reg",
            adapter="fake-api",
            config={"host": "acme.example", "allow_empty": True},
        )
    )
    db.commit()
    fake_adapter.listing = listing(3)
    r = client.post("/api/sources", json={"company_name": "Acme 2", "url": "https://acme.example"})
    assert r.status_code == 409 and "acme-reg" in r.json()["detail"]
