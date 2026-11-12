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
from app.core.schedule import FULL_AT, INCREMENTAL_MINUTES, TRACKED_AT, TZ
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


def build_scheduler(ctx: Ctx) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=TZ)
    common = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 600}
    sched.add_job(
        run_all,
        IntervalTrigger(minutes=INCREMENTAL_MINUTES, timezone=TZ),
        args=[ctx, "incremental"],
        id="incremental",
        **common,
    )
    sched.add_job(
        run_all,
        CronTrigger(hour=FULL_AT.hour, minute=FULL_AT.minute, timezone=TZ),
        args=[ctx, "full"],
        id="full",
        **common,
    )
    sched.add_job(
        run_all,
        CronTrigger(hour=TRACKED_AT.hour, minute=TRACKED_AT.minute, timezone=TZ),
        args=[ctx, "tracked"],
        id="tracked",
        **common,
    )
    sched.add_job(
        analysis_tick, IntervalTrigger(seconds=60, timezone=TZ), args=[ctx], id="analysis", **common
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
    await run_all(ctx, "incremental")  # do not wait 30 min for the first run
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
