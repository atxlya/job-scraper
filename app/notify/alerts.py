"""New tech-internship alerts. See docs/DESIGN.md §6.

Every job gets an `Alert` row once it has been dealt with, whether it was sent alone,
sent in a group, or quietly recorded during a source's first load. A job without
an Alert row is still owed one, which is how failed sends get retried.

A job sent alone carries Like / Applied / Dismiss buttons (app/notify/buttons.py). Its
message is always drawn whole by render_alert, from what the database says now, so an
edit for the eligibility result keeps the buttons and an edit for a press keeps the
eligibility line.
"""

import html
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.eligibility import eligibility
from app.core.models import Alert, Company, Job, JobAnalysis, JobUserState, Source
from app.notify.telegram import Buttons, TelegramChannel, TelegramError

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
BURST = 10
GROUP_LINES = 30


def _e(text: str | None) -> str:
    return html.escape(text or "", quote=True)


def _alertable(job: Job) -> bool:
    return job.is_internship is True and job.is_tech is True and job.state == "open"


def _eligibility_lines(job: Job, analysis: JobAnalysis | None) -> list[str]:
    e = eligibility(job, analysis)
    lines = []
    if e.degree:
        lines.append(f"⚠️ For {e.degree} students only (from the title)")
    flags = job.platform_flags or {}
    if flags.get("notice"):
        return [*lines, "📄 Government notice — eligibility is in the PDF"]
    if flags.get("partial"):
        return [*lines, "ℹ️ Details unavailable — open link"]
    if e.quote:
        lines.append(f"⚠️ Check: “{_e(e.quote)}”")
    if lines:
        return lines
    if e.status == "ok":
        return ["✅ Eligible — nothing in the posting rules you out"]
    if e.checking:
        return ["🔍 Checking eligibility…"]
    if not e.unclear:
        return ["❔ Eligibility not checked yet"]
    return ["❔ Eligibility unclear — read the posting"]


def format_alert(
    job: Job, company: Company, analysis: JobAnalysis | None, dashboard_url: str | None = None
) -> str:
    locs = job.locations or []
    where = ", ".join(locs[:3]) + (f" +{len(locs) - 3}" if len(locs) > 3 else "")
    if job.posted_at:
        d = job.posted_at.astimezone(IST)
        posted = f"Posted {d.day} {d:%b %Y}"
    else:
        posted = "Posted date not given"
    lines = [
        f"<b>{_e(company.name)}</b> · {_e(job.title)}",
        f"📍 {_e(where) or 'Location not given'}",
        f"🗓 {posted}",
        *_eligibility_lines(job, analysis),
        _links(job, dashboard_url),
    ]
    return "\n".join(lines)


def _links(job: Job, dashboard_url: str | None) -> str:
    flags = job.platform_flags or {}
    if flags.get("notice"):
        apply = (
            f'<a href="{_e(job.apply_url)}">Notice PDF</a>'
            if job.apply_url
            else f'<a href="{_e(job.url)}">Notice</a>'
        )
    elif flags.get("partial"):
        apply = f'<a href="{_e(job.url)}">Open link</a>'
    else:
        apply = f'<a href="{_e(job.apply_url or job.url)}">Apply</a>'
    if not dashboard_url:
        return apply
    return f'{apply} · <a href="{_e(dashboard_url.rstrip("/"))}/jobs/{job.id}">Dashboard</a>'


# tag: (code in the button's data, label, label while it is the job's tag)
TAG_BUTTONS = {
    "liked": ("l", "❤️ Like", "✓ Liked"),
    "applied": ("a", "✅ Applied", "✓ Applied"),
    "dismissed": ("d", "🗑 Dismiss", "✓ Dismissed"),
}
REMOVE = "-"


def tag_buttons(job_id: int, tag: str | None) -> Buttons:
    """One row of three. The data says what a press sets ("t:12:l" = liked, "t:12:-" =
    no tag), not "toggle", so a press handled twice, or on an out-of-date message,
    can't flip the tag back."""
    row = []
    for t, (code, label, current) in TAG_BUTTONS.items():
        if t == tag:
            row.append((current, f"t:{job_id}:{REMOVE}"))
        else:
            row.append((label, f"t:{job_id}:{code}"))
    return [row]


def render_alert(session: Session, job: Job, dashboard_url: str | None) -> tuple[str, Buttons]:
    company = session.get(Company, job.company_id)
    us = session.get(JobUserState, job.id, populate_existing=True)
    text = format_alert(job, company, _analysis(session, job.id), dashboard_url)
    return text, tag_buttons(job.id, us.tag if us else None)


def format_group(rows: list[tuple[Job, Company]]) -> str:
    out = [f"🆕 <b>{len(rows)} new tech internships</b>"]
    for job, company in rows[:GROUP_LINES]:
        out.append(f'• <b>{_e(company.name)}</b> · <a href="{_e(job.url)}">{_e(job.title)}</a>')
    if len(rows) > GROUP_LINES:
        out.append(f"…and {len(rows) - GROUP_LINES} more in the dashboard")
    return "\n".join(out)


def format_first_run(company: Company, n: int) -> str:
    return f"Loaded {n} existing internships from {_e(company.name)}"


def _analysis(session: Session, job_id: int) -> JobAnalysis | None:
    return session.scalars(select(JobAnalysis).where(JobAnalysis.job_id == job_id)).first()


def _owed(session: Session, source: Source) -> list[Job]:
    alerted = select(Alert.job_id)
    jobs = session.scalars(
        select(Job).where(
            Job.company_id == source.company_id,
            Job.is_internship.is_(True),
            Job.is_tech.is_(True),
            Job.state == "open",
            Job.id.not_in(alerted),
        )
    ).all()
    return [j for j in jobs if source.id in j.source_ids and _alertable(j)]


async def process_new(
    session: Session,
    channel: TelegramChannel | None,
    source: Source,
    new_job_ids: list[int],
    now: datetime,
    dashboard_url: str | None = None,
) -> None:
    company = session.get(Company, source.company_id)
    if not source.initial_load_done:
        jobs = [session.get(Job, i) for i in new_job_ids]
        n = sum(1 for j in jobs if j is not None and _alertable(j))
        message_id = None
        if channel is not None and n:
            try:
                message_id = await channel.send(format_first_run(company, n))
            except TelegramError:
                log.warning("first-run summary for %s not sent", source.key)
        for j in jobs:
            if j is not None:
                session.add(Alert(job_id=j.id, message_id=message_id, grouped=True, sent_at=now))
        source.initial_load_done = True
        session.flush()
        return

    if channel is None:
        return  # owed alerts stay owed until Telegram is configured
    owed = _owed(session, source)
    if not owed:
        return
    sent: list[tuple[int, int, bool]] = []  # (job_id, message_id, grouped)
    try:
        if len(owed) > BURST:
            message_id = await channel.send(format_group([(j, company) for j in owed]))
            sent = [(j.id, message_id, True) for j in owed]
        else:
            for j in owed:
                text, buttons = render_alert(session, j, dashboard_url)
                message_id = await channel.send(text, buttons)
                sent.append((j.id, message_id, False))
    except TelegramError as e:
        log.warning("telegram send failed for %s: %s (will retry)", source.key, e)
    # Written only after all sends: never hold a database write across a network wait.
    for job_id, message_id, grouped in sent:
        session.add(Alert(job_id=job_id, message_id=message_id, grouped=grouped, sent_at=now))
    session.flush()


async def refresh_after_analysis(
    session: Session,
    channel: TelegramChannel | None,
    job_id: int,
    now: datetime,
    dashboard_url: str | None = None,
) -> None:
    """Pass a fresh session: the message is read from the database while the lock is held."""
    if channel is None:
        return
    async with channel.message_lock:
        job = session.get(Job, job_id)
        if job is None:
            return
        alert = session.scalars(select(Alert).where(Alert.job_id == job_id)).first()
        text, buttons = render_alert(session, job, dashboard_url)
        try:
            if alert is None:
                if _alertable(job):  # classified as a tech internship only after analysis
                    mid = await channel.send(text, buttons)
                    session.add(Alert(job_id=job.id, message_id=mid, grouped=False, sent_at=now))
            elif not alert.grouped and alert.message_id is not None:
                await channel.edit(alert.message_id, text, buttons)
                alert.edited_at = now
        except TelegramError as e:
            log.warning("telegram update failed for job %s: %s", job_id, e)
        session.flush()
