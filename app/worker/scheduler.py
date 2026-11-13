"""The worker process: builds the context and runs the schedule forever.

python -m app.worker.scheduler
"""

import asyncio
import logging
from pathlib import Path

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.db import make_engine, make_session_factory
from app.core.registry import load_registry, sync_registry
from app.core.schedule import TZ, ScheduleConfig, load_schedule
from app.core.settings import Settings, get_settings
from app.http.client import PoliteClient
from app.pipeline.classify import load_keywords
from app.worker.runner import Ctx, analysis_tick, run_all

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger(__name__)


def build_ctx(settings: Settings) -> Ctx:
    sf = make_session_factory(make_engine(settings.database_url))
    provider = pacer = channel = None
    if settings.gemini_api_key:
        from app.llm.gemini import GeminiProvider  # noqa: PLC0415 - heavy import, optional
        from app.llm.pacer import Pacer  # noqa: PLC0415

        provider = GeminiProvider(settings.gemini_api_key, settings.gemini_model)
        pacer = Pacer(sf, rpm=settings.gemini_rpm, daily_cap=settings.gemini_daily_cap)
    if settings.telegram_bot_token and settings.telegram_chat_id:
        from app.notify.telegram import TelegramChannel  # noqa: PLC0415

        channel = TelegramChannel(
            settings.telegram_bot_token, settings.telegram_chat_id, httpx.AsyncClient()
        )
    return Ctx(
        settings=settings,
        session_factory=sf,
        client=PoliteClient(min_interval_s=settings.http_min_interval_s),
        provider=provider,
        pacer=pacer,
        channel=channel,
        keywords=load_keywords(ROOT / "config" / "keywords.yaml"),
    )


COMMON = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 600}


def _triggers(cfg: ScheduleConfig) -> dict[str, IntervalTrigger | CronTrigger]:
    return {
        "incremental": IntervalTrigger(minutes=cfg.incremental_minutes, timezone=TZ),
        "full": CronTrigger(hour=cfg.full_at.hour, minute=cfg.full_at.minute, timezone=TZ),
        "tracked": CronTrigger(hour=cfg.tracked_at.hour, minute=cfg.tracked_at.minute, timezone=TZ),
    }


class ScheduleWatch:
    """Re-reads the schedule saved from the dashboard and moves the jobs when it changes."""

    def __init__(self, sched: AsyncIOScheduler, ctx: Ctx, current: ScheduleConfig) -> None:
        self.sched, self.ctx, self.current = sched, ctx, current

    async def check(self) -> bool:
        with self.ctx.session_factory() as s:
            cfg = load_schedule(s)
        if cfg == self.current:
            return False
        for job_id, trigger in _triggers(cfg).items():
            self.sched.reschedule_job(job_id, trigger=trigger)
        log.info("schedule changed: %s", cfg)
        self.current = cfg
        return True


def build_scheduler(ctx: Ctx) -> AsyncIOScheduler:
    with ctx.session_factory() as s:
        cfg = load_schedule(s)
    sched = AsyncIOScheduler(timezone=TZ)
    for job_id, trigger in _triggers(cfg).items():
        sched.add_job(run_all, trigger, args=[ctx, job_id], id=job_id, **COMMON)
    sched.add_job(
        analysis_tick, IntervalTrigger(seconds=60, timezone=TZ), args=[ctx], id="analysis", **COMMON
    )
    sched.add_job(
        ScheduleWatch(sched, ctx, cfg).check,  # a bound async method: APScheduler awaits it
        IntervalTrigger(seconds=60, timezone=TZ),
        id="schedule",
        **COMMON,
    )
    return sched


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    ctx = build_ctx(settings)
    with ctx.session_factory() as s:
        sync_registry(s, load_registry(ROOT / "config" / "sources.yaml"))
        s.commit()
    if ctx.channel is None:
        log.warning("Telegram not configured: alerts are queued until it is")
    if ctx.provider is None:
        log.warning("Gemini not configured: jobs are stored without eligibility checks")
    sched = build_scheduler(ctx)
    sched.start()
    tasks = []  # held here so the event loop's weak reference isn't the only one
    if ctx.channel is not None:
        from app.worker.poller import poll_forever  # noqa: PLC0415

        tasks.append(asyncio.create_task(poll_forever(ctx)))  # the alerts' tag buttons
    await run_all(ctx, "incremental")  # do not wait for the first interval
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
