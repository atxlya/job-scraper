"""Reads Telegram button presses by long-polling getUpdates, for as long as the worker runs.

No webhook: the Pi is reachable only over Tailscale, so Telegram can't call in.
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.notify.buttons import handle_update, load_offset
from app.notify.telegram import TelegramError
from app.worker.runner import Ctx, _dash

log = logging.getLogger(__name__)
POLL_TIMEOUT = 50  # seconds Telegram holds the request open while nothing happens
FIRST_WAIT, MAX_WAIT = 5, 300


async def poll_once(ctx: Ctx, now: datetime | None = None) -> int:
    """One getUpdates call. Returns how many updates were handled."""
    with ctx.session_factory() as s:
        offset = load_offset(s)
    updates = await ctx.channel.get_updates(offset, POLL_TIMEOUT)
    handled = 0
    for u in sorted(updates, key=lambda u: u["update_id"]):
        if await handle_update(
            ctx.session_factory, ctx.channel, u, now or datetime.now(UTC), _dash(ctx)
        ):
            handled += 1
    return handled


async def poll_forever(ctx: Ctx, sleep=asyncio.sleep) -> None:
    wait = FIRST_WAIT
    while True:
        try:
            await poll_once(ctx)
            wait = FIRST_WAIT
            continue
        except TelegramError as e:
            log.warning("telegram getUpdates failed: %s (retrying in %ss)", e, wait)
        except Exception:  # noqa: BLE001 - a bad update must not stop the buttons for good
            log.exception("handling Telegram button presses failed (retrying in %ss)", wait)
        await sleep(wait)
        wait = min(wait * 2, MAX_WAIT)
