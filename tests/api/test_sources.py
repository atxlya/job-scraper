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
        "rejected": 0,
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


# --- Sources page: status order, nightly chart, last run, run history (prompt 3) ---


def _sources(db):
    return {s.key: s for s in db.scalars(select(Source))}


def _run(db, src, kind, started, *, status="ok", minutes=2, found=10, total=None, error=None):
    from datetime import timedelta

    from app.core.models import ScrapeRun

    r = ScrapeRun(
        source_id=src.id,
        kind=kind,
        status=status,
        started_at=started,
        finished_at=started + timedelta(minutes=minutes),
        jobs_found=found,
        reported_total=total,
        new_count=1,
        updated_count=2,
        closed_count=3,
        error=error,
    )
    db.add(r)
    db.commit()
    return r


def test_sources_order_failing_by_streak_then_partial_and_warning_then_ok(client, app, db):
    app.dependency_overrides[now] = lambda: NOW
    for name in ["Zeta", "Alpha", "Beta", "Gamma", "Delta", "Eta", "Theta"]:
        seed_job(db, company=name)
    s = _sources(db)
    for k in s:
        s[k].last_success_at = NOW - HOUR
    s["alpha"].consecutive_failures = 2
    s["zeta"].consecutive_failures = 5
    s["gamma"].warning_active = True
    s["theta"].last_success_at = None
    s["eta"].enabled = False
    db.commit()
    _run(
        db,
        s["delta"],
        "incremental",
        NOW - HOUR,
        status="partial",
        error="2 of 51 job pages failed",
    )
    _run(db, s["beta"], "incremental", NOW - 2 * HOUR, status="partial")
    _run(
        db, s["beta"], "incremental", NOW - HOUR, status="ok"
    )  # recovered: only the last run counts
    rows = client.get("/api/sources").json()
    assert [(r["key"], r["status"]) for r in rows] == [
        ("zeta", "failing"),
        ("alpha", "failing"),
        ("delta", "partial"),
        ("gamma", "warning"),
        ("beta", "ok"),
        ("theta", "never_run"),
        ("eta", "ok"),  # turned off: last, whatever its state
    ]


def test_sources_last_run_kind_and_duration(client, app, db):
    app.dependency_overrides[now] = lambda: NOW
    seed_job(db, company="Alpha")
    src = _sources(db)["alpha"]
    _run(db, src, "full", NOW - 8 * HOUR, minutes=90)
    _run(db, src, "incremental", NOW - HOUR, minutes=2)
    row = client.get("/api/sources").json()[0]
    assert row["last_run"] == {
        "kind": "incremental",
        "status": "ok",
        "started_at": "2026-11-11T03:30:00Z",
        "duration_s": 120,
    }


def test_sources_nights_one_point_per_ist_night_from_full_runs(client, app, db):
    from datetime import timedelta

    app.dependency_overrides[now] = lambda: NOW  # 10:00 IST on 11 Nov
    seed_job(db, company="Alpha")
    src = _sources(db)["alpha"]
    two_am_ist = datetime(2026, 11, 10, 20, 30, tzinfo=UTC)  # 02:00 IST on 11 Nov
    _run(db, src, "full", two_am_ist, found=40)  # 11 Nov
    _run(db, src, "full", two_am_ist - DAY, found=30, status="failed", error="boom")  # 10 Nov
    _run(db, src, "full", two_am_ist - 2 * DAY, found=10)  # 9 Nov: an earlier run…
    _run(
        db, src, "full", two_am_ist - 2 * DAY + timedelta(hours=3), found=38
    )  # …and the later one wins
    _run(db, src, "incremental", two_am_ist + HOUR, found=5)  # ignored
    _run(db, src, "full", two_am_ist - 14 * DAY, found=99)  # 28 Oct: older than 14 nights
    nights = client.get("/api/sources").json()[0]["nights"]
    assert len(nights) == 14
    assert nights[0]["day"] == "2026-10-29" and nights[-1]["day"] == "2026-11-11"
    assert nights[-1] == {"day": "2026-11-11", "count": 40, "status": "ok"}
    assert nights[-2] == {"day": "2026-11-10", "count": 30, "status": "failed"}
    assert nights[-3] == {"day": "2026-11-09", "count": 38, "status": "ok"}
    assert nights[-4] == {"day": "2026-11-08", "count": None, "status": None}


def test_source_runs_newest_first_at_most_20(client, app, db):
    from datetime import timedelta

    seed_job(db, company="Alpha")
    src = _sources(db)["alpha"]
    for i in range(25):
        _run(db, src, "incremental", NOW - timedelta(minutes=30 * i), found=i, total=95)
    _run(
        db, src, "full", NOW + HOUR, minutes=91, status="failed", error="ParseError: x", total=None
    )
    runs = client.get("/api/sources/alpha/runs").json()
    assert len(runs) == 20
    assert runs[0] == {
        "kind": "full",
        "status": "failed",
        "started_at": "2026-11-11T05:30:00Z",
        "duration_s": 91 * 60,
        "jobs_found": 10,
        "reported_total": None,
        "new_count": 1,
        "updated_count": 2,
        "closed_count": 3,
        "error": "ParseError: x",
    }
    assert [r["jobs_found"] for r in runs[1:4]] == [0, 1, 2]


def test_source_runs_unknown_source(client):
    assert client.get("/api/sources/nope/runs").status_code == 404


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (NOW, "2026-11-11T20:30:00Z"),  # 10:00 IST → 02:00 IST tomorrow
        (datetime(2026, 11, 10, 19, 30, tzinfo=UTC), "2026-11-10T20:30:00Z"),  # 01:00 IST → today
    ],
)
def test_schedule_next_full_sweep(client, app, at, expected):
    app.dependency_overrides[now] = lambda: at
    assert client.get("/api/schedule").json() == {
        "next_full_at": expected,
        "incremental_minutes": 30,
        "full_at": "02:00",
        "tracked_at": "04:00",
        "next_tracked_at": "2026-11-11T22:30:00Z" if at == NOW else "2026-11-10T22:30:00Z",
    }


def test_schedule_change_is_saved(client, app):
    app.dependency_overrides[now] = lambda: NOW  # 10:00 IST
    body = {"incremental_minutes": 45, "full_at": "01:30", "tracked_at": "11:00"}
    r = client.put("/api/schedule", json=body)
    assert r.status_code == 200
    assert r.json() == {
        **body,
        "next_full_at": "2026-11-11T20:00:00Z",  # 01:30 IST tomorrow
        "next_tracked_at": "2026-11-11T05:30:00Z",  # 11:00 IST today
    }
    assert client.get("/api/schedule").json() == r.json()


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"incremental_minutes": 5, "full_at": "02:00", "tracked_at": "04:00"}, "at least 15"),
        ({"incremental_minutes": 30, "full_at": "02:00", "tracked_at": "02:20"}, "an hour apart"),
    ],
)
def test_schedule_change_rejected(client, body, detail):
    r = client.put("/api/schedule", json=body)
    assert r.status_code == 422 and detail in r.json()["detail"]
    assert client.get("/api/schedule").json()["incremental_minutes"] == 30  # unchanged


@pytest.mark.parametrize("bad", ["2:00", "24:00", "02:60", "noon"])
def test_schedule_bad_time_format(client, bad):
    body = {"incremental_minutes": 30, "full_at": bad, "tracked_at": "04:00"}
    assert client.put("/api/schedule", json=body).status_code == 422


def test_schedule_change_needs_login(anon):
    body = {"incremental_minutes": 45, "full_at": "01:30", "tracked_at": "11:00"}
    assert anon.put("/api/schedule", json=body).status_code == 401
