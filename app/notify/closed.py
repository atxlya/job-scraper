""" "🔒 Closed" messages for jobs you liked or applied to. See docs/DESIGN.md §6.

Run after each round of sources, so jobs closed in one round (by a "not found" page or
by missing two complete sweeps, DESIGN §3) go out together. It looks at the jobs'
state, not at what the round did, so a job closed some other way (the dashboard
fetching a page that has gone) is reported after the next round.

A job is reported at most once, ever: `closed_alerts` is unique on the job. A row is
written only after the message is sent, so a failed send is retried next round.
"""

import html
import logging
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.models import ClosedAlert, Company, Job, JobUserState, TagHistory
from app.notify.telegram import TelegramChannel, TelegramError

log = logging.getLogger(__name__)
GROUP_LINES = 30


def _e(text: str | None) -> str:
    return html.escape(text or "", quote=True)


def _link(job: Job, dashboard_url: str | None) -> tuple[str, str]:
    if dashboard_url:
        return f"{dashboard_url.rstrip('/')}/jobs/{job.id}", "Dashboard"
    return job.url, "Posting"


def format_closed(rows: list[tuple[Job, Company]], dashboard_url: str | None) -> str:
    if len(rows) == 1:
        job, company = rows[0]
        url, label = _link(job, dashboard_url)
        return (
            f"🔒 Closed: <b>{_e(company.name)}</b> · {_e(job.title)}\n"
            f'<a href="{_e(url)}">{label}</a>'
        )
    out = [f"🔒 <b>{len(rows)} jobs you liked or applied to have closed</b>"]
    for job, company in rows[:GROUP_LINES]:
        url, _ = _link(job, dashboard_url)
        out.append(f'• <b>{_e(company.name)}</b> · <a href="{_e(url)}">{_e(job.title)}</a>')
    if len(rows) > GROUP_LINES:
        out.append(f"…and {len(rows) - GROUP_LINES} more in the dashboard")
    return "\n".join(out)


def _owed(session: Session) -> list[tuple[Job, Company]]:
    # Tagged before it closed: liking a job that had already closed isn't news.
    tagged_after_close = exists().where(TagHistory.job_id == Job.id, TagHistory.at > Job.closed_at)
    rows = session.execute(
        select(Job, Company)
        .join(Company, Company.id == Job.company_id)
        .join(JobUserState, JobUserState.job_id == Job.id)
        .where(
            Job.state == "closed",
            JobUserState.tag.in_(["liked", "applied"]),
            Job.id.not_in(select(ClosedAlert.job_id)),
            ~tagged_after_close,
        )
        .order_by(Company.name, Job.title, Job.id)
    )
    return [(job, company) for job, company in rows]


async def notify_closed(
    session: Session,
    channel: TelegramChannel | None,
    now: datetime,
    dashboard_url: str | None = None,
) -> None:
    if channel is None:
        return  # owed until Telegram is configured
    rows = _owed(session)
    if not rows:
        return
    try:
        message_id = await channel.send(format_closed(rows, dashboard_url))
    except TelegramError as e:
        log.warning("closed-job message not sent: %s (will retry)", e)
        return
    for job, _ in rows:
        session.add(ClosedAlert(job_id=job.id, message_id=message_id, sent_at=now))
    session.flush()
