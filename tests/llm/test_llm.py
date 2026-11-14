from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.db import make_engine, make_session_factory
from app.core.models import Base, Company, Job, JobAnalysis, LlmUsage
from app.llm.pacer import PACIFIC, Pacer
from app.llm.provider import Analysis, RateLimited, Sections, validate_quotes
from app.llm.queue import next_jobs, run_analysis_batch

T0 = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)  # 22:00 on 9 Nov in Pacific time

TEXT = (
    "<p>Interns build tools.</p>"
    "<p>Must be currently enrolled at a university in the United States.</p>"
)


def analysis(quote=None, eligibility="ok"):
    return Analysis(
        sections=Sections(
            about="a",
            responsibilities=["r"],
            requirements=["q"],
            preferred=[],
            eligibility=[quote] if quote else [],
        ),
        is_internship=True,
        is_tech=True,
        eligibility=eligibility,
        eligibility_quote=quote,
    )


class FakeTime:
    def __init__(self, start=T0):
        self.now = start

    def clock(self):
        return self.now

    async def sleep(self, s):
        self.now += timedelta(seconds=s)


@pytest.fixture
def sf():
    eng = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return make_session_factory(eng)


def add_job(s, ext, first_seen, countries=("IN",), intern=True, tech=True, desc=TEXT):
    c = s.scalars(select(Company)).first()
    if c is None:
        c = Company(slug="g", name="Google")
        s.add(c)
        s.flush()
    j = Job(
        company_id=c.id,
        external_id=ext,
        url="u",
        title=f"Intern {ext}",
        description_html=desc,
        country_codes=list(countries),
        content_hash="h",
        is_internship=intern,
        is_tech=tech,
        first_seen_at=first_seen,
        last_seen_at=first_seen,
        source_ids=[1],
    )
    s.add(j)
    s.flush()
    return j


# --- quote validation -------------------------------------------------------


def test_rejects_hallucinated_quote():
    a = validate_quotes(analysis("Must hold a US passport", "warn"), TEXT)
    assert a.eligibility == "unknown" and a.eligibility_quote is None


def test_accepts_quote_with_whitespace_differences():
    q = "Must be currently   enrolled at a university\nin the United States."
    a = validate_quotes(analysis(q, "warn"), TEXT)
    assert a.eligibility == "warn" and a.eligibility_quote == q


def test_ok_without_quote_stays_ok():
    assert validate_quotes(analysis(), TEXT).eligibility == "ok"


# --- pacer -------------------------------------------------------------------


async def test_pacer_blocks_sixth_request_in_minute(sf):
    ft = FakeTime()
    p = Pacer(sf, rpm=5, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    for _ in range(5):
        assert await p.acquire()
    assert ft.now == T0
    assert await p.acquire()
    assert ft.now >= T0 + timedelta(seconds=60)


async def test_pacer_daily_cap(sf):
    ft = FakeTime()
    p = Pacer(sf, rpm=1000, daily_cap=3, clock=ft.clock, sleep=ft.sleep)
    assert [await p.acquire() for _ in range(4)] == [True, True, True, False]


async def test_pacer_resets_at_pacific_midnight(sf):
    ft = FakeTime()
    p = Pacer(sf, rpm=1000, daily_cap=1, clock=ft.clock, sleep=ft.sleep)
    assert await p.acquire()
    assert not await p.acquire()
    ft.now = T0 + timedelta(hours=2, minutes=1)  # 00:01 on 10 Nov, Pacific
    assert await p.acquire()
    with sf() as s:
        days = sorted(u.day.isoformat() for u in s.scalars(select(LlmUsage)))
    assert days == ["2026-11-09", "2026-11-10"]


async def test_one_rate_limit_pauses_then_continues(sf):
    ft = FakeTime()
    p = Pacer(sf, rpm=1000, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    for _ in range(50):
        await p.acquire()
    p.on_rate_limited()
    before = ft.now
    assert await p.acquire()  # waits out the 120 s pause first
    assert ft.now >= before + timedelta(seconds=120)


async def test_second_rate_limit_stops_today_and_learns_cap(sf):
    ft = FakeTime()
    p = Pacer(sf, rpm=1000, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    for _ in range(50):
        await p.acquire()
    p.on_rate_limited()
    p.on_rate_limited()
    assert not await p.acquire()
    with sf() as s:
        assert s.scalars(select(LlmUsage)).one().effective_cap == 50
    ft.now = T0 + timedelta(days=1)
    assert [await p.acquire() for _ in range(31)][-2:] == [True, False]  # learned cap 30


# --- queue -------------------------------------------------------------------


def test_queue_new_before_backlog(sf):
    with sf() as s:
        old_in = add_job(s, "old-in", T0 - timedelta(days=2))
        new_us = add_job(s, "new-us", T0, countries=("US",))
        got = next_jobs(s, 10, fresh_since=T0 - timedelta(minutes=30))
        assert [j.id for j in got] == [new_us.id, old_in.id]


def test_queue_india_first_within_backlog(sf):
    with sf() as s:
        us = add_job(s, "us", T0 - timedelta(days=1), countries=("US",))
        ind = add_job(s, "in", T0 - timedelta(days=3))
        got = next_jobs(s, 10, fresh_since=T0)
        assert [j.id for j in got] == [ind.id, us.id]


def test_queue_skips_known_non_tech_or_non_intern(sf):
    with sf() as s:
        add_job(s, "hr", T0, tech=False)
        add_job(s, "senior", T0, intern=False)
        unclear = add_job(s, "grad", T0, intern=None, tech=None)
        assert [j.id for j in next_jobs(s, 10, fresh_since=T0)] == [unclear.id]


class FakeProvider:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, 0

    async def analyze(self, title, text):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result

    async def classify_titles(self, titles):
        return [(True, True)] * len(titles)


async def test_batch_stores_validated_analysis(sf):
    with sf() as s:
        j = add_job(s, "a", T0)
        s.commit()
    ft = FakeTime()
    pacer = Pacer(sf, rpm=100, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    prov = FakeProvider(analysis("Must hold a US passport", "warn"))
    ids = await run_analysis_batch(sf, prov, pacer, model="m", now=T0)
    with sf() as s:
        a = s.scalars(select(JobAnalysis)).one()
        assert ids == [j.id] and a.eligibility == "unknown"
        assert s.get(Job, j.id).analysis_state == "done"


async def test_provider_failure_marks_failed_keeps_job(sf):
    with sf() as s:
        j = add_job(s, "a", T0)
        s.commit()
    ft = FakeTime()
    pacer = Pacer(sf, rpm=100, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    await run_analysis_batch(sf, FakeProvider(exc=RuntimeError("boom")), pacer, model="m", now=T0)
    with sf() as s:
        job = s.get(Job, j.id)
        assert job.analysis_state == "failed" and job.title == "Intern a"


async def test_rate_limit_leaves_job_pending(sf):
    with sf() as s:
        j = add_job(s, "a", T0)
        s.commit()
    ft = FakeTime()
    pacer = Pacer(sf, rpm=100, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    await run_analysis_batch(sf, FakeProvider(exc=RateLimited()), pacer, model="m", now=T0)
    with sf() as s:
        assert s.get(Job, j.id).analysis_state == "pending"


async def test_unclear_job_gets_classification_from_analysis(sf):
    with sf() as s:
        j = add_job(s, "g", T0, intern=None, tech=None)
        s.commit()
    ft = FakeTime()
    pacer = Pacer(sf, rpm=100, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    await run_analysis_batch(sf, FakeProvider(analysis()), pacer, model="m", now=T0)
    with sf() as s:
        job = s.get(Job, j.id)
        assert job.is_internship is True and job.is_tech is True


def test_prompt_flags_degree_level_for_a_bachelors_student():
    from app.llm.gemini import PROMPT  # noqa: PLC0415
    from app.llm.queue import PROMPT_VERSION  # noqa: PLC0415

    assert "Bachelor's" in PROMPT and "PhD or Master's" in PROMPT
    assert PROMPT_VERSION == "2"


# --- busy server, title triage ------------------------------------------------


async def test_busy_server_leaves_job_pending_and_pauses(sf):
    from app.llm.provider import Busy  # noqa: PLC0415

    with sf() as s:
        j = add_job(s, "a", T0)
        add_job(s, "b", T0 - timedelta(days=1))
        s.commit()
    ft = FakeTime()
    pacer = Pacer(sf, rpm=100, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    prov = FakeProvider(exc=Busy("503"))
    assert await run_analysis_batch(sf, prov, pacer, model="m", now=T0) == []
    assert prov.calls == 1  # stops at the first busy answer
    with sf() as s:
        assert {x.analysis_state for x in s.scalars(select(Job))} == {"pending"}
    before = ft.now
    assert await pacer.acquire()  # next request waits out the pause
    assert ft.now - before == timedelta(seconds=120)
    with sf() as s:
        assert s.get(Job, j.id).analysis_state == "pending"


class TitleProvider(FakeProvider):
    def __init__(self, answers=None, exc=None):
        super().__init__()
        self.answers, self.exc, self.seen = answers or {}, exc, []

    async def classify_titles(self, titles):
        self.seen.append(list(titles))
        if self.exc:
            raise self.exc
        return [self.answers.get(t, (False, False)) for t in titles]


async def test_triage_settles_unclear_titles_in_one_request(sf):
    from app.llm.queue import triage_titles  # noqa: PLC0415

    with sf() as s:
        a = add_job(s, "a", T0, intern=None, tech=None)
        b = add_job(s, "b", T0 - timedelta(hours=1), intern=True, tech=None)
        add_job(s, "c", T0, intern=True, tech=True)  # already clear
        add_job(s, "d", T0, intern=False, tech=None)  # already out of the queue
        s.commit()
    ft = FakeTime()
    pacer = Pacer(sf, rpm=100, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    prov = TitleProvider({"Intern a": (True, True), "Intern b": (False, False)})
    assert await triage_titles(sf, prov, pacer) == [a.id, b.id]
    assert prov.seen == [["Intern a", "Intern b"]]
    with sf() as s:
        ja, jb = s.get(Job, a.id), s.get(Job, b.id)
        assert (ja.is_internship, ja.is_tech) == (True, True)
        assert (jb.is_internship, jb.is_tech) == (True, False)  # known field kept
        assert [j.id for j in next_jobs(s, 10, fresh_since=T0)][0] == a.id
        assert b.id not in [j.id for j in next_jobs(s, 10, fresh_since=T0)]
        assert s.get(LlmUsage, T0.astimezone(PACIFIC).date()).requests == 1


async def test_triage_batches_and_does_nothing_when_all_clear(sf):
    from app.llm.queue import triage_titles  # noqa: PLC0415

    with sf() as s:
        for i in range(25):
            add_job(s, f"u{i:02}", T0 - timedelta(minutes=i), intern=None, tech=None)
        s.commit()
    ft = FakeTime()
    pacer = Pacer(sf, rpm=100, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
    prov = TitleProvider()
    assert len(await triage_titles(sf, prov, pacer)) == 20
    assert len(await triage_titles(sf, prov, pacer)) == 5
    assert await triage_titles(sf, prov, pacer) == []
    assert [len(b) for b in prov.seen] == [20, 5]


async def test_triage_failure_changes_nothing(sf):
    from app.llm.provider import Busy  # noqa: PLC0415
    from app.llm.queue import triage_titles  # noqa: PLC0415

    with sf() as s:
        j = add_job(s, "a", T0, intern=None, tech=None)
        s.commit()
    for exc in (Busy("503"), RateLimited(), ValueError("classification count mismatch")):
        ft = FakeTime()
        pacer = Pacer(sf, rpm=100, daily_cap=100, clock=ft.clock, sleep=ft.sleep)
        assert await triage_titles(sf, TitleProvider(exc=exc), pacer) == []
        with sf() as s:
            job = s.get(Job, j.id)
            assert (job.is_internship, job.is_tech, job.analysis_state) == (None, None, "pending")


async def test_triage_respects_daily_cap(sf):
    from app.llm.queue import triage_titles  # noqa: PLC0415

    with sf() as s:
        add_job(s, "a", T0, intern=None, tech=None)
        s.commit()
    ft = FakeTime()
    pacer = Pacer(sf, rpm=100, daily_cap=0, clock=ft.clock, sleep=ft.sleep)
    prov = TitleProvider()
    assert await triage_titles(sf, prov, pacer) == []
    assert prov.seen == []


def test_gemini_maps_server_errors_to_busy():
    import asyncio  # noqa: PLC0415

    from google.genai import errors  # noqa: PLC0415

    from app.llm.gemini import GeminiProvider  # noqa: PLC0415
    from app.llm.provider import Busy  # noqa: PLC0415

    p = GeminiProvider(api_key="k", model="m")

    async def raise_(code):
        raise errors.APIError(code, {"error": {"code": code, "message": "x"}})

    for code, want in ((503, Busy), (500, Busy), (429, RateLimited), (400, errors.APIError)):
        p._client.aio.models.generate_content = lambda **kw: raise_(code)  # noqa: B023
        with pytest.raises(want):
            asyncio.run(p.analyze("t", "x"))
