import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from app.core.db import make_engine, make_session_factory
from app.core.models import Alert, Base, Company, Job, JobAnalysis, ScrapeRun, Source
from app.notify.alerts import format_alert, process_new, refresh_after_analysis
from app.notify.health import notify_round, record_run
from app.notify.telegram import TelegramChannel

T0 = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
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
        m.edit = m.post(f"{API}/editMessageText").mock(
            return_value=httpx.Response(200, json={"ok": True, "result": {}})
        )
        yield m


@pytest.fixture
def channel():
    return TelegramChannel("TOKEN", "42", httpx.AsyncClient())


def make_source(session, key="google", loaded=True):
    c = Company(slug=key, name=key.title())
    session.add(c)
    session.flush()
    s = Source(company_id=c.id, key=key, adapter="google", config={}, initial_load_done=loaded)
    session.add(s)
    session.flush()
    return c, s


def make_job(session, src, ext, title="Software Engineering Intern", intern=True, tech=True):
    j = Job(
        company_id=src.company_id,
        source_ids=[src.id],
        external_id=ext,
        url=f"https://x/{ext}",
        apply_url=f"https://x/{ext}/apply",
        title=title,
        locations=["Bengaluru, India"],
        country_codes=["IN"],
        content_hash="h",
        is_internship=intern,
        is_tech=tech,
        first_seen_at=T0,
        last_seen_at=T0,
        posted_at=T0,
    )
    session.add(j)
    session.flush()
    return j


def sent_texts(tg):
    return [json.loads(c.request.content)["text"] for c in tg.send.calls]


def test_format_alert_escapes_html(session):
    c, s = make_source(session)
    j = make_job(session, s, "1", title="R&D <Intern> 🚀")
    text = format_alert(j, c, None)
    assert "R&amp;D &lt;Intern&gt; 🚀" in text
    assert text.splitlines()[0] == "<b>Google</b> · R&amp;D &lt;Intern&gt; 🚀"
    assert "📍 Bengaluru, India" in text and "🗓 Posted 10 Nov 2026" in text
    assert "🔍 Checking eligibility…" in text
    assert '<a href="https://x/1/apply">Apply</a>' in text


def test_format_alert_eligibility_lines(session):
    c, s = make_source(session)
    j = make_job(session, s, "1")
    warn = JobAnalysis(
        job_id=j.id,
        model="m",
        prompt_version="1",
        sections={},
        eligibility="warn",
        eligibility_quote="US students only",
        created_at=T0,
    )
    ok = JobAnalysis(
        job_id=j.id, model="m", prompt_version="1", sections={}, eligibility="ok", created_at=T0
    )
    assert "⚠️ Check: “US students only”" in format_alert(j, c, warn)
    assert "✅ Eligible — nothing in the posting rules you out" in format_alert(j, c, ok)
    j.analysis_state = "failed"
    assert "❔ Eligibility not checked yet" in format_alert(j, c, None)


async def test_first_run_sends_summary_only(session, tg, channel):
    c, s = make_source(session, loaded=False)
    ids = [make_job(session, s, str(i)).id for i in range(3)]
    ids.append(make_job(session, s, "hr", title="HR Intern", tech=False).id)
    await process_new(session, channel, s, ids, T0)
    assert sent_texts(tg) == ["Loaded 3 existing internships from Google"]
    assert s.initial_load_done is True
    assert len(session.scalars(select(Alert)).all()) == 4  # all handled, none re-alerted later


async def test_burst_over_10_grouped(session, tg, channel):
    c, s = make_source(session)
    ids = [make_job(session, s, str(i)).id for i in range(11)]
    await process_new(session, channel, s, ids, T0)
    assert tg.send.call_count == 1
    alerts = session.scalars(select(Alert)).all()
    assert len(alerts) == 11 and all(a.grouped and a.message_id == 1 for a in alerts)


async def test_exactly_10_sent_individually(session, tg, channel):
    c, s = make_source(session)
    ids = [make_job(session, s, str(i)).id for i in range(10)]
    await process_new(session, channel, s, ids, T0)
    assert tg.send.call_count == 10


async def test_never_alerts_twice(session, tg, channel):
    c, s = make_source(session)
    ids = [make_job(session, s, "1").id]
    await process_new(session, channel, s, ids, T0)
    await process_new(session, channel, s, ids, T0)
    assert tg.send.call_count == 1


async def test_non_tech_internship_not_alerted(session, tg, channel):
    c, s = make_source(session)
    ids = [make_job(session, s, "hr", title="HR Intern", tech=False).id]
    await process_new(session, channel, s, ids, T0)
    assert tg.send.call_count == 0


async def test_edit_after_analysis(session, tg, channel):
    c, s = make_source(session)
    j = make_job(session, s, "1")
    await process_new(session, channel, s, [j.id], T0)
    session.add(
        JobAnalysis(
            job_id=j.id, model="m", prompt_version="1", sections={}, eligibility="ok", created_at=T0
        )
    )
    session.flush()
    await refresh_after_analysis(session, channel, j.id, T0)
    body = json.loads(tg.edit.calls.last.request.content)
    assert body["message_id"] == 1 and "✅ Eligible" in body["text"]


async def test_late_classified_job_alerted_after_analysis(session, tg, channel):
    c, s = make_source(session)
    j = make_job(session, s, "g", title="Graduate Programme", intern=None, tech=None)
    await process_new(session, channel, s, [j.id], T0)
    assert tg.send.call_count == 0
    j.is_internship, j.is_tech = True, True
    session.add(
        JobAnalysis(
            job_id=j.id, model="m", prompt_version="1", sections={}, eligibility="ok", created_at=T0
        )
    )
    session.flush()
    await refresh_after_analysis(session, channel, j.id, T0)
    assert tg.send.call_count == 1 and "✅ Eligible" in sent_texts(tg)[0]


async def test_telegram_down_does_not_crash_run(session, channel):
    c, s = make_source(session)
    j = make_job(session, s, "1")
    with respx.mock() as m:
        m.post(f"{API}/sendMessage").mock(return_value=httpx.Response(502))
        await process_new(session, channel, s, [j.id], T0)
    assert session.scalars(select(Alert)).all() == []  # retried on the next run


async def test_unsent_alert_retried_next_run(session, channel):
    c, s = make_source(session)
    j = make_job(session, s, "1")
    with respx.mock() as m:
        route = m.post(f"{API}/sendMessage").mock(
            side_effect=[
                httpx.Response(502),
                httpx.Response(200, json={"ok": True, "result": {"message_id": 7}}),
            ]
        )
        await process_new(session, channel, s, [j.id], T0)
        await process_new(session, channel, s, [], T0 + timedelta(minutes=30))
    assert route.call_count == 2
    assert session.scalars(select(Alert)).one().message_id == 7


# --- health ------------------------------------------------------------------


def run(session, src, status, found=0, kind="incremental", at=T0):
    r = ScrapeRun(
        source_id=src.id,
        kind=kind,
        status=status,
        started_at=at,
        finished_at=at,
        jobs_found=found,
        error=None if status != "failed" else "boom",
    )
    session.add(r)
    session.flush()
    record_run(session, src, r, at)
    return r


async def test_three_failures_warns_once_per_day(session, tg, channel):
    others = [make_source(session, f"s{i}")[1] for i in range(4)]
    c, s = make_source(session, "intel")
    for i in range(5):
        at = T0 + timedelta(minutes=30 * i)
        runs = [run(session, s, "failed", at=at)] + [
            run(session, o, "ok", 5, at=at) for o in others
        ]
        await notify_round(session, channel, runs, at)
    texts = sent_texts(tg)
    assert len(texts) == 1 and "intel" in texts[0]


async def test_count_drop_over_half_warns(session, tg, channel):
    c, s = make_source(session, "cisco")
    others = [make_source(session, f"s{i}")[1] for i in range(4)]
    r1 = run(session, s, "ok", 1400, kind="full")
    await notify_round(session, channel, [r1], T0)
    r2 = run(session, s, "ok", 600, kind="full", at=T0 + timedelta(days=1))
    await notify_round(
        session, channel, [r2] + [run(session, o, "ok", 5) for o in others], T0 + timedelta(days=1)
    )
    texts = sent_texts(tg)
    assert len(texts) == 1 and "1400" in texts[0] and "600" in texts[0]


async def test_incremental_count_never_compared_to_full(session, tg, channel):
    c, s = make_source(session, "cisco")
    await notify_round(session, channel, [run(session, s, "ok", 1400, kind="full")], T0)
    await notify_round(session, channel, [run(session, s, "ok", 60)], T0 + timedelta(hours=1))
    assert tg.send.call_count == 0


async def test_recovered_message(session, tg, channel):
    others = [make_source(session, f"s{i}")[1] for i in range(4)]
    c, s = make_source(session, "intel")
    for _ in range(3):
        await notify_round(
            session,
            channel,
            [run(session, s, "failed")] + [run(session, o, "ok", 5) for o in others],
            T0,
        )
    await notify_round(session, channel, [run(session, s, "ok", 10)], T0 + timedelta(hours=2))
    texts = sent_texts(tg)
    assert len(texts) == 2 and texts[1].startswith("✅ intel recovered")


async def test_all_sources_failing_sends_one_message(session, tg, channel):
    sources = [make_source(session, f"s{i}")[1] for i in range(28)]
    for i in range(3):
        at = T0 + timedelta(minutes=30 * i)
        await notify_round(
            session, channel, [run(session, s, "failed", at=at) for s in sources], at
        )
    texts = sent_texts(tg)
    assert len(texts) == 1 and "28 of 28 sources failing" in texts[0]


async def test_owed_query_filters_in_sql(session, tg, channel):
    from sqlalchemy import event

    c, s = make_source(session)
    for i in range(50):
        make_job(session, s, f"x{i}", title="Senior Engineer", intern=False)
    make_job(session, s, "1")
    statements: list[str] = []
    event.listen(
        session.bind,
        "before_cursor_execute",
        lambda conn, cur, stmt, params, ctx, many: statements.append(stmt),
    )
    await process_new(session, channel, s, [], T0)
    owed_query = next(q for q in statements if "FROM jobs" in q and "alerts" in q)
    where = owed_query.split("WHERE", 1)[1]
    assert "is_internship" in where and "is_tech" in where and "state" in where
    assert tg.send.call_count == 1


def test_degree_only_title_warns_even_when_analysis_says_ok(session):
    c, s = make_source(session)
    j = make_job(session, s, "1", title="Software Engineering PhD Intern, Summer 2027")
    ok = JobAnalysis(
        job_id=j.id, model="m", prompt_version="2", sections={}, eligibility="ok", created_at=T0
    )
    for analysis in (None, ok):
        text = format_alert(j, c, analysis)
        assert "⚠️ For PhD students only (from the title)" in text
        assert "✅ Eligible" not in text


def test_degree_only_title_keeps_the_posting_quote(session):
    c, s = make_source(session)
    j = make_job(session, s, "1", title="Data Science Intern - Masters")
    warn = JobAnalysis(
        job_id=j.id,
        model="m",
        prompt_version="2",
        sections={},
        eligibility="warn",
        eligibility_quote="Must be enrolled at a US university",
        created_at=T0,
    )
    text = format_alert(j, c, warn)
    assert "⚠️ For Master's students only (from the title)" in text
    assert "⚠️ Check: “Must be enrolled at a US university”" in text


def test_dashboard_link_when_configured(session):
    c, s = make_source(session)
    j = make_job(session, s, "1")
    text = format_alert(j, c, None, dashboard_url="http://pi:8000/")
    assert f'<a href="http://pi:8000/jobs/{j.id}">Dashboard</a>' in text
    assert "Dashboard" not in format_alert(j, c, None)


async def test_process_new_passes_dashboard_link(session, tg, channel):
    c, s = make_source(session)
    j = make_job(session, s, "1")
    await process_new(session, channel, s, [j.id], T0, dashboard_url="http://pi:8000")
    assert f"/jobs/{j.id}" in sent_texts(tg)[0]
