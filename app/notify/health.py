"""Scraper health warnings over Telegram. See docs/DESIGN.md §6.

record_run() updates a source's counters after each run. notify_round() runs once
after a whole round of sources: if most of the round failed it sends one
"network down?" message instead of one warning per source.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import ScrapeRun, Setting, Source
from app.notify.telegram import TelegramChannel, TelegramError

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
FAIL_STREAK = 3
DROP_RATIO = 0.5
GLOBAL_SHARE = 0.8
GLOBAL_MIN_SOURCES = 3
GLOBAL_KEY = "global_outage_warned_at"
GLOBAL_REPEAT = timedelta(hours=6)


def record_run(session: Session, source: Source, run: ScrapeRun, now: datetime) -> None:
    if run.status == "failed":
        source.consecutive_failures += 1
        source.last_error = run.error
    else:
        source.consecutive_failures = 0
        source.last_success_at = now
        source.last_job_count = run.jobs_found
    session.flush()


def _previous_full(session: Session, run: ScrapeRun) -> ScrapeRun | None:
    return session.scalars(
        select(ScrapeRun)
        .where(
            ScrapeRun.source_id == run.source_id,
            ScrapeRun.kind == "full",
            ScrapeRun.status.in_(["ok", "partial"]),
            ScrapeRun.id < run.id,
        )
        .order_by(ScrapeRun.id.desc())
    ).first()


def _problem(session: Session, source: Source, run: ScrapeRun) -> str | None:
    if run.status == "failed" and source.consecutive_failures >= FAIL_STREAK:
        return (
            f"⚠️ <b>{source.key}</b> failed {source.consecutive_failures} runs in a row: "
            f"{(run.error or '')[:300]}"
        )
    if run.status != "failed" and run.kind == "full":
        prev = _previous_full(session, run)
        if prev and prev.jobs_found and run.jobs_found < DROP_RATIO * prev.jobs_found:
            return (
                f"⚠️ <b>{source.key}</b> job count dropped from {prev.jobs_found} "
                f"to {run.jobs_found} — the site may have changed"
            )
    return None


async def _send(channel: TelegramChannel | None, text: str) -> bool:
    if channel is None:
        return False
    try:
        await channel.send(text)
        return True
    except TelegramError as e:
        log.warning("health message not sent: %s", e)
        return False


async def notify_round(
    session: Session, channel: TelegramChannel | None, runs: list[ScrapeRun], now: datetime
) -> None:
    failed = [r for r in runs if r.status == "failed"]
    if len(runs) >= GLOBAL_MIN_SOURCES and len(failed) >= GLOBAL_SHARE * len(runs):
        setting = session.get(Setting, GLOBAL_KEY)
        last = datetime.fromisoformat(setting.value["at"]) if setting else None
        if last is None or now - last >= GLOBAL_REPEAT:
            text = f"⚠️ {len(failed)} of {len(runs)} sources failing — network down?"
            if await _send(channel, text):
                if setting is None:
                    session.add(Setting(key=GLOBAL_KEY, value={"at": now.isoformat()}))
                else:
                    setting.value = {"at": now.isoformat()}
        session.flush()
        return  # per-source warnings would only repeat the same news

    today = now.astimezone(IST).date()
    for run in runs:
        source = session.get(Source, run.source_id)
        if source is None:
            continue
        if run.status == "ok" and source.warning_active:
            if await _send(channel, f"✅ {source.key} recovered"):
                source.warning_active = False
            continue
        problem = _problem(session, source, run)
        if problem is None:
            continue
        if source.last_warned_at and source.last_warned_at.astimezone(IST).date() == today:
            continue
        if await _send(channel, problem):
            source.last_warned_at = now
            source.warning_active = True
    session.flush()
