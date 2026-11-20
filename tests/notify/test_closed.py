""" "🔒 Closed" messages for liked and applied jobs. See docs/DESIGN.md §6."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from app.core.db import make_engine, make_session_factory
from app.core.models import Base, ClosedAlert, Company, Job, Source
from app.core.tags import set_tag
from app.notify.closed import notify_closed
from app.notify.telegram import TelegramChannel

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
LATER = T0 + timedelta(days=1)
API = "https://api.telegram.org/botTOKEN"


@pytest.fixture
def session():
    eng = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as s:
        yield s


@pytest.fixture
def tg():
    with respx.mock(assert_all_called=False) as m:
        counter = {"n": 0}

        def ok(request):
            counter["n"] += 1
            return httpx.Response(200, json={"ok": True, "result": {"message_id": counter["n"]}})

        m.send = m.post(f"{API}/sendMessage").mock(side_effect=ok)
        yield m


@pytest.fixture
def channel():
    return TelegramChannel("TOKEN", "42", httpx.AsyncClient())


_n = iter(range(10_000))


def job(session, tag=None, title="Software Intern", company="Google", tagged_at=T0):
    c = session.scalars(select(Company).where(Company.name == company)).first()
    if c is None:
        c = Company(slug=company.lower(), name=company)
        session.add(c)
        session.flush()
        session.add(Source(company_id=c.id, key=c.slug, adapter="google"))
    ext = str(next(_n))
    j = Job(
        company_id=c.id,
        external_id=ext,
        url=f"https://x/{ext}",
        title=title,
        content_hash="h",
        first_seen_at=T0 - timedelta(days=5),
        last_seen_at=T0,
    )
    session.add(j)
    session.flush()
    if tag:
        set_tag(session, j.id, tag, tagged_at)
    return j


def close(j, at=LATER):
    j.state, j.closed_at = "closed", at


def texts(tg):
    return [json.loads(c.request.content)["text"] for c in tg.send.calls]


async def test_one_liked_job_closing(session, tg, channel):
    j = job(session, "liked", title="R&D Intern")
    close(j)
    await notify_closed(session, channel, LATER, "http://pi:8000/")
    assert texts(tg) == [
        f'🔒 Closed: <b>Google</b> · R&amp;D Intern\n<a href="http://pi:8000/jobs/{j.id}">Dashboard</a>'
    ]
    row = session.scalars(select(ClosedAlert)).one()
    assert (row.job_id, row.message_id, row.sent_at) == (j.id, 1, LATER)


async def test_only_liked_and_applied_jobs(session, tg, channel):
    for tag in ("dismissed", None, "applied"):
        close(job(session, tag, title=f"Intern {tag}"))
    await notify_closed(session, channel, LATER, None)
    assert len(texts(tg)) == 1 and "Intern applied" in texts(tg)[0]


async def test_open_jobs_send_nothing(session, tg, channel):
    job(session, "liked")
    await notify_closed(session, channel, LATER, None)
    assert tg.send.call_count == 0


async def test_several_closing_send_one_grouped_message(session, tg, channel):
    a = job(session, "liked", title="Data Intern")
    b = job(session, "applied", title="SWE Intern", company="NVIDIA")
    close(a), close(b)
    await notify_closed(session, channel, LATER, "http://pi:8000")
    [text] = texts(tg)
    assert text.splitlines() == [
        "🔒 <b>2 jobs you liked or applied to have closed</b>",
        f'• <b>Google</b> · <a href="http://pi:8000/jobs/{a.id}">Data Intern</a>',
        f'• <b>NVIDIA</b> · <a href="http://pi:8000/jobs/{b.id}">SWE Intern</a>',
    ]
    assert {r.message_id for r in session.scalars(select(ClosedAlert))} == {1}


async def test_without_dashboard_url_links_the_posting(session, tg, channel):
    j = job(session, "liked")
    close(j)
    await notify_closed(session, channel, LATER, None)
    assert f'<a href="https://x/{j.external_id}">Posting</a>' in texts(tg)[0]


async def test_at_most_once_per_job_even_after_reopening(session, tg, channel):
    j = job(session, "liked")
    close(j)
    await notify_closed(session, channel, LATER, None)
    await notify_closed(session, channel, LATER, None)
    j.state, j.closed_at = "open", None  # back on the site
    close(j, LATER + timedelta(days=3))  # and gone again
    await notify_closed(session, channel, LATER + timedelta(days=3), None)
    assert tg.send.call_count == 1


async def test_tagging_a_job_that_had_already_closed_sends_nothing(session, tg, channel):
    j = job(session)
    close(j)
    set_tag(session, j.id, "liked", LATER + timedelta(hours=1))
    await notify_closed(session, channel, LATER + timedelta(hours=2), None)
    assert tg.send.call_count == 0


async def test_failed_send_is_retried_next_time(session, channel):
    j = job(session, "applied")
    close(j)
    with respx.mock() as m:
        route = m.post(f"{API}/sendMessage").mock(
            side_effect=[
                httpx.Response(502),
                httpx.Response(200, json={"ok": True, "result": {"message_id": 9}}),
            ]
        )
        await notify_closed(session, channel, LATER, None)
        assert session.scalars(select(ClosedAlert)).all() == []
        await notify_closed(session, channel, LATER, None)
    assert route.call_count == 2
    assert session.scalars(select(ClosedAlert)).one().message_id == 9


async def test_no_channel_keeps_them_owed(session, tg, channel):
    close(job(session, "liked"))
    await notify_closed(session, None, LATER, None)
    assert session.scalars(select(ClosedAlert)).all() == []
    await notify_closed(session, channel, LATER, None)
    assert tg.send.call_count == 1


async def test_long_group_is_cut_short(session, tg, channel):
    for i in range(35):
        close(job(session, "liked", title=f"Intern {i}"))
    await notify_closed(session, channel, LATER, None)
    [text] = texts(tg)
    assert text.splitlines()[0] == "🔒 <b>35 jobs you liked or applied to have closed</b>"
    assert text.splitlines()[-1] == "…and 5 more in the dashboard"
    assert len(session.scalars(select(ClosedAlert)).all()) == 35


async def test_rejected_applications_get_no_closed_message(session, tg, channel):
    from app.core.tags import set_stage  # noqa: PLC0415

    rejected = job(session, "applied", title="Rejected Intern")
    set_stage(session, rejected.id, "rejected", T0)
    live = job(session, "applied", title="Interviewing Intern")
    set_stage(session, live.id, "interview", T0)
    close(rejected)
    close(live)
    await notify_closed(session, channel, LATER, None)
    assert len(texts(tg)) == 1 and "Interviewing Intern" in texts(tg)[0]
