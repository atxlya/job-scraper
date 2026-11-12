"""Runs one source end to end: fetch → store → classify → alert → health. After a whole
round, it also reports liked/applied jobs that closed.

Database rule: a write is never left open while waiting on the network. Each run
fetches everything first, then writes and commits in one step, then sends alerts.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import ADAPTERS, GONE, ParseError, RawJob
from app.core.models import Company, Job, JobUserState, ScrapeRun, Source
from app.http.client import PoliteClient, RobotsDisallowed
from app.llm.queue import run_analysis_batch
from app.notify.alerts import process_new, refresh_after_analysis
from app.notify.closed import notify_closed
from app.notify.health import notify_round, record_run
from app.pipeline.classify import Keywords, classify
from app.pipeline.derived import refresh_derived
from app.pipeline.ingest import ingest, job_key, mark_gone, raw_from_job

log = logging.getLogger(__name__)
RunKind = Literal["incremental", "full", "tracked"]
CONCURRENCY = 4
COUNT_TOLERANCE = 0.02
# A job page failing in one of these ways skips that job, not the whole source. Only
# JSONDecodeError (a 200 answer that isn't JSON), not every ValueError: an adapter bug
# (a pydantic error, int("")) must still fail the run loudly.
DETAIL_ERRORS = (httpx.HTTPError, ParseError, RobotsDisallowed, json.JSONDecodeError)


@dataclass
class Ctx:
    settings: Any
    session_factory: sessionmaker[Session]
    client: PoliteClient
    provider: Any
    pacer: Any
    channel: Any
    keywords: Keywords
    source_locks: dict[int, asyncio.Lock] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(UTC)


def _dash(ctx: Ctx) -> str | None:
    return getattr(ctx.settings, "dashboard_url", None)  # tests run with settings=None


def _mismatch(found: int, total: int | None) -> bool:
    return total is not None and abs(found - total) > max(2, COUNT_TOLERANCE * total)


async def run_source(ctx: Ctx, source_id: int, mode: RunKind) -> ScrapeRun:
    lock = ctx.source_locks.setdefault(source_id, asyncio.Lock())
    async with lock:  # the 30-min and nightly runs must not scrape one source at once
        return await _run_source(ctx, source_id, mode)


async def _run_source(ctx: Ctx, source_id: int, mode: RunKind) -> ScrapeRun:
    started = _now()
    with ctx.session_factory() as s:
        src = s.get(Source, source_id)
        adapter = ADAPTERS[src.adapter]()
        cfg = dict(src.config)
        # Jobs stored without a description (detail page failed) count as unknown, so their
        # details are retried on the next run.
        known = set(
            s.scalars(
                select(Job.external_id).where(
                    Job.company_id == src.company_id,
                    Job.description_html.is_not(None),
                    Job.description_html != "",
                )
            )
        )
        targets: list[tuple[int, RawJob]] = []
        if mode == "tracked":
            tagged = set(
                s.scalars(
                    select(JobUserState.job_id).where(JobUserState.tag.in_(["liked", "applied"]))
                )
            )
            for job in s.scalars(
                select(Job).where(Job.company_id == src.company_id, Job.state == "open")
            ):
                if source_id in job.source_ids and (job.id in tagged or src.adapter == "google"):
                    targets.append((job.id, raw_from_job(job)))

    status, error, result, gone_ids = "ok", None, None, []
    try:
        if mode == "tracked":
            failures: list[str] = []
            for job_id, raw in targets:
                try:
                    if await adapter.fetch_detail(ctx.client, cfg, raw) is GONE:
                        gone_ids.append(job_id)
                except DETAIL_ERRORS as e:
                    # One job failing must not stop the re-check of the others.
                    log.warning("%s: re-check failed for %s: %s", src.key, raw.external_id, e)
                    if len(failures) == len(targets) - 1:
                        raise  # every job failed: the site, not one job, is the problem
                    failures.append(f"{raw.external_id}: {type(e).__name__}: {e}")
            if failures:
                status = "partial"
                error = (f"{len(failures)} of {len(targets)} jobs failed; " + "; ".join(failures))[
                    :2000
                ]
        else:
            result = await adapter.list_jobs(ctx.client, cfg, mode)
            if mode == "full" and _mismatch(len(result.jobs), result.reported_total):
                status = "partial"
                result = result.model_copy(update={"complete": False})
            fresh: list[RawJob] = []
            tried = failed = 0
            has_details = getattr(adapter, "listing_has_details", False)
            for raw in result.jobs:
                c = classify(raw, ctx.keywords)
                if has_details and raw.description_html:
                    fresh.append(raw)  # the listing already carries the whole posting
                    continue
                if job_key(raw) in known or c.is_internship is False or c.is_tech is False:
                    # Details only for possible tech internships: a first full sweep would
                    # otherwise fetch tens of thousands of pages (Accenture alone ~40k).
                    fresh.append(raw)
                    continue
                tried += 1
                try:
                    detail = await adapter.fetch_detail(ctx.client, cfg, raw)
                except DETAIL_ERRORS as e:
                    log.warning("%s: detail failed for %s: %s", src.key, raw.external_id, e)
                    failed += 1
                    error = f"{failed} of {tried} job pages failed; last: {type(e).__name__}: {e}"
                    fresh.append(raw)
                    continue
                if detail is not GONE:
                    fresh.append(detail)
            if tried >= 2 and failed == tried:
                # Every job page failing means the site changed, not one bad job: say so.
                status, error = "partial", error[:2000]
            else:
                error = None
            result = result.model_copy(update={"jobs": fresh})
    except Exception as e:  # noqa: BLE001 - one source failing must never stop the others
        log.warning("%s %s run failed: %s", src.key, mode, e)
        status, error = "failed", f"{type(e).__name__}: {e}"[:2000]

    new_ids: list[int] = []
    with ctx.session_factory() as s:
        src = s.get(Source, source_id)
        run = ScrapeRun(
            source_id=source_id, kind=mode, status=status, started_at=started, error=error
        )
        try:
            if status != "failed":
                now = _now()
                if mode == "tracked":
                    for job_id in gone_ids:
                        mark_gone(s, s.get(Job, job_id), now)
                    run.jobs_found, run.closed_count = len(targets), len(gone_ids)
                else:
                    stats = ingest(s, src, result, mode, now)
                    _classify_new(s, ctx.keywords, stats.new_ids)
                    refresh_derived(s, stats.new_ids + stats.updated_ids)
                    new_ids = stats.new_ids
                    run.jobs_found = stats.seen
                    run.reported_total = result.reported_total
                    run.new_count, run.updated_count = len(stats.new_ids), len(stats.updated_ids)
                    run.closed_count = len(stats.closed_ids)
            run.finished_at = _now()
            s.add(run)
            s.flush()
            record_run(s, src, run, run.finished_at)
            s.commit()
        except Exception as e:  # noqa: BLE001
            log.exception("%s: storing results failed", source_id)
            s.rollback()
            src = s.get(Source, source_id)
            run = ScrapeRun(
                source_id=source_id,
                kind=mode,
                status="failed",
                started_at=started,
                finished_at=_now(),
                error=f"store: {type(e).__name__}: {e}"[:2000],
            )
            s.add(run)
            s.flush()
            record_run(s, src, run, run.finished_at)
            s.commit()
            new_ids = []

    if run.status != "failed" and mode != "tracked":
        try:
            with ctx.session_factory() as s:
                await process_new(
                    s, ctx.channel, s.get(Source, source_id), new_ids, _now(), _dash(ctx)
                )
                s.commit()
        except Exception:  # noqa: BLE001 - owed alerts are retried next run
            log.exception("%s: alert step failed", source_id)
    return run


def _classify_new(s: Session, kw: Keywords, job_ids: list[int]) -> None:
    for job_id in job_ids:
        job = s.get(Job, job_id)
        c = classify(raw_from_job(job), kw)
        job.is_internship, job.is_tech = c.is_internship, c.is_tech
        flags = job.platform_flags or {}
        settled = c.is_internship is not None and c.is_tech is not None
        if (
            c.is_internship is False
            or c.is_tech is False
            or flags.get("partial")  # title-only: nothing for Gemini to read
            or flags.get("snippet")  # a search summary: Gemini can only answer "unknown"
            or (flags.get("notice") and settled)  # PDF notice: only unclear titles need Gemini
        ):
            job.analysis_state = "skipped"  # not a tech internship, or nothing to ask
    s.flush()


async def run_all(ctx: Ctx, mode: RunKind, only: str | None = None) -> list[ScrapeRun]:
    with ctx.session_factory() as s:
        q = (
            select(Source.id, Source.key)
            .join(Company, Company.id == Source.company_id)
            .where(Source.enabled.is_(True), Company.supported.is_(True))
        )
        ids = [sid for sid, key in s.execute(q) if only is None or key == only]
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(sid: int) -> ScrapeRun:
        async with sem:
            return await run_source(ctx, sid, mode)

    runs = await asyncio.gather(*(one(sid) for sid in ids))
    try:
        with ctx.session_factory() as s:
            attached = [s.get(ScrapeRun, r.id) for r in runs]
            await notify_round(s, ctx.channel, attached, _now())
            s.commit()
    except Exception:  # noqa: BLE001 - health messages must not break the schedule
        log.exception("health notifications failed")
    try:
        with ctx.session_factory() as s:
            await notify_closed(s, ctx.channel, _now(), _dash(ctx))
            s.commit()
    except Exception:  # noqa: BLE001 - owed "closed" messages are retried next round
        log.exception("closed-job notifications failed")
    return list(runs)


async def analysis_tick(ctx: Ctx) -> list[int]:
    if ctx.provider is None or ctx.pacer is None:
        return []
    now = _now()
    ids = await run_analysis_batch(
        ctx.session_factory,
        ctx.provider,
        ctx.pacer,
        model=ctx.settings.gemini_model,
        now=now,
        fresh_since=now - timedelta(minutes=35),
    )
    for job_id in ids:
        with ctx.session_factory() as s:
            await refresh_after_analysis(s, ctx.channel, job_id, _now(), _dash(ctx))
            s.commit()
    return ids
