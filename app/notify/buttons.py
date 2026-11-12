"""Like / Applied / Dismiss presses on Telegram alerts. See docs/DESIGN.md §6.

The dashboard is reachable only over Tailscale, so Telegram can't call a webhook; the
worker long-polls getUpdates instead (app/worker/poller.py) and hands each update here.

Each update is handled once: the tag change and the next getUpdates offset are committed
together, before anything is sent back to Telegram. Only then are the press answered and
the message redrawn; if the worker stops between the two, the tag is set and only the
redraw is lost.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from app.core.models import Job, JobUserState, Setting
from app.core.tags import STAGE_LABEL, set_tag
from app.notify.alerts import REMOVE, TAG_BUTTONS, render_alert
from app.notify.telegram import TelegramChannel, TelegramError

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
OFFSET_KEY = "telegram_update_offset"
DATA = re.compile(r"t:(\d{1,12}):([a-z-])")
CODES = {code: tag for tag, (code, _, _) in TAG_BUTTONS.items()} | {REMOVE: None}
DONE = {"liked": "Liked", "applied": "Applied", "dismissed": "Dismissed", None: "Tag removed"}


def load_offset(s: Session) -> int | None:
    row = s.get(Setting, OFFSET_KEY)
    return int(row.value["offset"]) if row else None


def _save_offset(s: Session, offset: int) -> None:
    row = s.get(Setting, OFFSET_KEY)
    if row is None:
        s.add(Setting(key=OFFSET_KEY, value={"offset": offset}))
    else:
        row.value = {"offset": offset}


@dataclass
class _Reply:
    callback_id: str
    text: str
    message_id: int | None = None  # set when the press changed (or confirmed) a tag
    job_id: int | None = None


def _apply(s: Session, chat_id: str, update: dict, now: datetime) -> _Reply | None:
    cq = update.get("callback_query")
    if not cq:
        return None  # only presses are asked for; anything else is skipped
    message = cq.get("message") or {}
    if str((message.get("chat") or {}).get("id")) != str(chat_id):
        return None  # not our chat: no answer at all
    m = DATA.fullmatch(cq.get("data") or "")
    if m is None or m.group(2) not in CODES:
        return _Reply(cq["id"], "Unknown button")
    job_id, tag = int(m.group(1)), CODES[m.group(2)]
    if s.get(Job, job_id) is None:
        return _Reply(cq["id"], "Job not found")
    us = s.get(JobUserState, job_id)
    if us is not None and us.tag == "applied" and us.stage and tag != "applied":
        # One tap would throw the stage away (you chose: confirm on the job page instead).
        label = STAGE_LABEL[us.stage]
        return _Reply(
            cq["id"], f"At {label}: change it on the dashboard", message.get("message_id"), job_id
        )
    # The dashboard's form dates "Applied" with today; the keyboard's `a` does the same.
    event_date = now.astimezone(IST).date() if tag == "applied" else None
    set_tag(s, job_id, tag, now, event_date=event_date)
    return _Reply(cq["id"], DONE[tag], message.get("message_id"), job_id)


async def handle_update(
    sf: sessionmaker[Session],
    channel: TelegramChannel,
    update: dict,
    now: datetime,
    dashboard_url: str | None = None,
) -> bool:
    """Returns False for an update already handled (its id is below the stored offset)."""
    with sf() as s:
        offset = load_offset(s)
        if offset is not None and update["update_id"] < offset:
            return False
        try:
            reply = _apply(s, channel.chat_id, update, now)
        except Exception:  # noqa: BLE001 - skip it, or the same update would block every later one
            log.exception("Telegram update %s could not be handled; skipped", update["update_id"])
            s.rollback()
            reply = None
        _save_offset(s, update["update_id"] + 1)
        s.commit()
    if reply is None:
        return True
    try:
        await channel.answer_callback(reply.callback_id, reply.text)
    except TelegramError as e:
        log.warning("button answer not sent: %s", e)  # e.g. "query is too old"
    if reply.message_id is None:
        return True
    async with channel.message_lock:
        with sf() as s:
            job = s.get(Job, reply.job_id)
            text, buttons = render_alert(s, job, dashboard_url)
        try:
            await channel.edit(reply.message_id, text, buttons)
        except TelegramError as e:
            log.warning("alert for job %s not redrawn: %s", reply.job_id, e)
    return True
