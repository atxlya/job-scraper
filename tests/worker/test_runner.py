import asyncio
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.adapters.base import GONE, ListingResult, ParseError, RawJob, register
from app.core.db import make_engine, make_session_factory
from app.core.models import Alert, Base, Company, Job, JobUserState, ScrapeRun, Source
from app.http.client import PoliteClient
from app.pipeline.classify import load_keywords
from app.pipeline.derived import create_fts
from app.worker.runner import Ctx, run_all, run_source
from app.worker.scheduler import build_scheduler

T0 = datetime(2026, 11, 10, tzinfo=UTC)
KEYWORDS = Path(__file__).resolve().parents[2] / "config" / "keywords.yaml"
DETAIL_CALLS: Counter = Counter()


@register
class FakeAdapter:
    name = "fake-test"

    async def list_jobs(self, client, cfg, mode):
        await asyncio.sleep(0)
        if cfg.get("boom"):
            raise ParseError("site changed")
        jobs = [RawJob(external_id=e, title=t, url=f"https://f/{e}") for e, t in cfg["jobs"]]
        return ListingResult(
            jobs=jobs, reported_total=cfg.get("total", len(jobs)), complete=mode == "full"
        )

    async def fetch_detail(self, client, cfg, job):
        DETAIL_CALLS[cfg["name"]] += 1
        await asyncio.sleep(0)
        if job.external_id in cfg.get("detail_down", []):
            raise httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known")
        if job.external_id in cfg.get("gone", []):
            return GONE
        return job.model_copy(update={"description_html": f"<p>{job.title}</p>"})


class SlowChannel:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, html):
        await asyncio.sleep(0.01)
        self.sent.append(html)
        return len(self.sent)

    async def edit(self, message_id, html):
        await asyncio.sleep(0.01)


@pytest.fixture
def ctx(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(eng)
    create_fts(eng)
    sf = make_session_factory(eng)
    DETAIL_CALLS.clear()
    return Ctx(
        settings=None,
        session_factory=sf,
        client=PoliteClient(min_interval_s=0),
        provider=None,
        pacer=None,
        channel=SlowChannel(),
        keywords=load_keywords(KEYWORDS),
    )


def add_source(ctx, name, loaded=True, **cfg):
    with ctx.session_factory() as s:
        c = Company(slug=name, name=name)
        s.add(c)
        s.flush()
        src = Source(
            company_id=c.id,
            key=name,
            adapter="fake-test",
            initial_load_done=loaded,
            config={"name": name, "jobs": [], **cfg},
        )
        s.add(src)
        s.commit()
        return src.id


def statuses(ctx):
    with ctx.session_factory() as s:
        return {s.get(Source, r.source_id).key: r.status for r in s.scalars(select(ScrapeRun))}


async def test_failing_source_does_not_stop_others(ctx):
    add_source(ctx, "a", jobs=[["1", "Software Intern"]])
    add_source(ctx, "b", boom=True)
    add_source(ctx, "c", jobs=[["2", "Data Intern"]])
    runs = await run_all(ctx, "incremental")
    assert len(runs) == 3
    assert statuses(ctx) == {"a": "ok", "b": "failed", "c": "ok"}
    with ctx.session_factory() as s:
        assert (
            "site changed"
            in s.scalars(select(ScrapeRun).where(ScrapeRun.status == "failed")).one().error
        )


async def test_count_mismatch_marks_partial_and_skips_close(ctx):
    sid = add_source(ctx, "m", jobs=[["1", "Software Intern"], ["2", "QA Intern"]])
    await run_source(ctx, sid, "full")
    with ctx.session_factory() as s:
        src = s.get(Source, sid)
        src.config = {**src.config, "jobs": [["1", "Software Intern"]], "total": 100}
        s.commit()
    for _ in range(2):
        run = await run_source(ctx, sid, "full")
        assert run.status == "partial"
    with ctx.session_factory() as s:
        assert {j.external_id: j.state for j in s.scalars(select(Job))} == {
            "1": "open",
            "2": "open",
        }


async def test_details_fetched_only_for_new(ctx):
    sid = add_source(ctx, "d", jobs=[["1", "Software Intern"]])
    await run_source(ctx, sid, "incremental")
    await run_source(ctx, sid, "incremental")
    assert DETAIL_CALLS["d"] == 1
    with ctx.session_factory() as s:
        assert s.scalars(select(Job)).one().description_html == "<p>Software Intern</p>"


async def test_gone_in_detail_is_not_stored(ctx):
    sid = add_source(ctx, "g", jobs=[["1", "Software Intern"], ["2", "QA Intern"]], gone=["2"])
    await run_source(ctx, sid, "incremental")
    with ctx.session_factory() as s:
        assert [j.external_id for j in s.scalars(select(Job))] == ["1"]


async def test_new_jobs_classified_and_alerted(ctx):
    sid = add_source(ctx, "n", jobs=[["1", "Software Engineering Intern"], ["2", "HR Intern"]])
    await run_source(ctx, sid, "incremental")
    with ctx.session_factory() as s:
        jobs = {j.external_id: j for j in s.scalars(select(Job))}
        assert (jobs["1"].is_internship, jobs["1"].is_tech) == (True, True)
        assert jobs["2"].analysis_state == "skipped"
    assert len(ctx.channel.sent) == 1 and "Software Engineering Intern" in ctx.channel.sent[0]


async def test_concurrent_sources_on_file_db(ctx):
    for i in range(6):
        add_source(ctx, f"s{i}", jobs=[[f"{i}-{k}", f"Software Intern {k}"] for k in range(3)])
    runs = await run_all(ctx, "incremental")
    assert [r.status for r in runs] == ["ok"] * 6
    with ctx.session_factory() as s:
        assert len(s.scalars(select(Alert)).all()) == 18


async def test_tracked_marks_gone(ctx):
    sid = add_source(ctx, "t", jobs=[["1", "Software Intern"]])
    await run_source(ctx, sid, "incremental")
    with ctx.session_factory() as s:
        job = s.scalars(select(Job)).one()
        s.add(JobUserState(job_id=job.id, tag="liked"))
        src = s.get(Source, sid)
        src.config = {**src.config, "gone": ["1"]}
        s.commit()
    run = await run_source(ctx, sid, "tracked")
    assert run.status == "ok" and run.closed_count == 1
    with ctx.session_factory() as s:
        assert s.scalars(select(Job)).one().state == "closed"


def test_scheduler_jobs_registered(ctx):
    sched = build_scheduler(ctx)
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == {"incremental", "full", "tracked", "analysis"}
    assert jobs["incremental"].trigger.interval.total_seconds() == 1800
    assert jobs["analysis"].trigger.interval.total_seconds() == 60
    assert str(jobs["full"].trigger.timezone) == "Asia/Kolkata"
    assert "hour='2'" in str(jobs["full"].trigger) and "hour='4'" in str(jobs["tracked"].trigger)
    assert jobs["incremental"].max_instances == 1 and jobs["incremental"].coalesce is True


async def test_details_skipped_for_non_candidates(ctx):
    sid = add_source(
        ctx,
        "nc",
        jobs=[
            ["1", "Senior Software Engineer"],
            ["2", "HR Intern"],
            ["3", "Software Intern"],
            ["4", "Graduate Programme"],
        ],
    )
    await run_source(ctx, sid, "incremental")
    assert DETAIL_CALLS["nc"] == 2  # only the intern and the unclear one need details
    with ctx.session_factory() as s:
        assert len(s.scalars(select(Job)).all()) == 4  # everything is still stored


class BrokenChannel(SlowChannel):
    async def send(self, html):
        raise RuntimeError("unexpected")


async def test_alert_step_crash_does_not_break_round(ctx):
    ctx.channel = BrokenChannel()
    add_source(ctx, "x", jobs=[["1", "Software Intern"]])
    add_source(ctx, "y", jobs=[["2", "Data Intern"]])
    runs = await run_all(ctx, "incremental")
    assert [r.status for r in runs] == ["ok", "ok"]


async def test_failed_detail_retried_next_run(ctx):
    sid = add_source(ctx, "r", jobs=[["1", "Software Intern"]], detail_down=["1"])
    await run_source(ctx, sid, "incremental")
    with ctx.session_factory() as s:
        assert s.scalars(select(Job)).one().description_html is None  # stored from the listing
        src = s.get(Source, sid)
        src.config = {**src.config, "detail_down": []}  # network back
        s.commit()
    await run_source(ctx, sid, "incremental")
    with ctx.session_factory() as s:
        assert s.scalars(select(Job)).one().description_html == "<p>Software Intern</p>"
    await run_source(ctx, sid, "incremental")
    assert DETAIL_CALLS["r"] == 2  # once it has a description, it is not fetched again


async def test_scraped_jobs_are_searchable_and_degree_flagged(ctx):
    from sqlalchemy import text  # noqa: PLC0415

    sid = add_source(ctx, "fts", jobs=[["1", "Compiler PhD Intern"]])
    await run_source(ctx, sid, "incremental")
    with ctx.session_factory() as s:
        hits = s.execute(text("SELECT rowid FROM jobs_fts WHERE jobs_fts MATCH '\"compiler\"*'"))
        job = s.scalars(select(Job)).one()
        assert [r[0] for r in hits] == [job.id]
        assert job.degree_only == "PhD"


DETAILED_CALLS: Counter = Counter()


@register
class DetailedListingAdapter:
    """A listing that already carries the description (Lever, Amazon, ...)."""

    name = "fake-detailed"
    listing_has_details = True

    async def list_jobs(self, client, cfg, mode):
        jobs = [
            RawJob(
                external_id=e,
                title="Software Engineer Intern",
                url=f"https://f/{e}",
                description_html=desc,
            )
            for e, desc in cfg["jobs"]
        ]
        return ListingResult(jobs=jobs, reported_total=len(jobs), complete=mode == "full")

    async def fetch_detail(self, client, cfg, job):
        DETAILED_CALLS[job.external_id] += 1
        return job.model_copy(update={"description_html": "<p>from detail</p>"})


def _add_detailed(ctx, jobs):
    with ctx.session_factory() as s:
        c = Company(slug="det", name="Det")
        s.add(c)
        s.flush()
        src = Source(company_id=c.id, key="det", adapter="fake-detailed", config={"jobs": jobs})
        s.add(src)
        s.commit()
        return src.id


async def test_listing_details_skip_detail_fetch(ctx):
    DETAILED_CALLS.clear()
    sid = _add_detailed(ctx, [["1", "<p>from listing</p>"]])
    await run_source(ctx, sid, "incremental")
    assert DETAILED_CALLS["1"] == 0
    with ctx.session_factory() as s:
        assert s.scalars(select(Job)).one().description_html == "<p>from listing</p>"


async def test_listing_details_without_description_still_fetches(ctx):
    DETAILED_CALLS.clear()
    sid = _add_detailed(ctx, [["2", None]])
    await run_source(ctx, sid, "incremental")
    assert DETAILED_CALLS["2"] == 1
    with ctx.session_factory() as s:
        assert s.scalars(select(Job)).one().description_html == "<p>from detail</p>"


def test_partial_and_settled_notices_skip_gemini(ctx):
    from app.worker.runner import _classify_new

    src_id = add_source(ctx, "gov")
    with ctx.session_factory() as s:
        src = s.get(Source, src_id)

        def add(ext, title, flags):
            j = Job(
                company_id=src.company_id,
                source_ids=[src.id],
                external_id=ext,
                url=f"https://x/{ext}",
                title=title,
                locations=[],
                country_codes=["IN"],
                platform_flags=flags,
                content_hash="h",
                first_seen_at=T0,
                last_seen_at=T0,
            )
            s.add(j)
            s.flush()
            return j

        partial = add(
            "p", "Software engineering internship trizetto product house", {"partial": True}
        )
        settled = add("n1", "Paid Internship for Engineering Students", {"notice": True})
        unclear = add("n2", "Paid Internship for UG/PG Students", {"notice": True})
        _classify_new(s, ctx.keywords, [partial.id, settled.id, unclear.id])
        assert (settled.is_internship, settled.is_tech) == (True, True)
        assert (unclear.is_internship, unclear.is_tech) == (True, None)
        assert partial.analysis_state == "skipped"
        assert settled.analysis_state == "skipped"
        assert unclear.analysis_state == "pending"
