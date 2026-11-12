"""Like / Applied / Dismiss buttons on job alerts, read by getUpdates long-polling."""

import json
from datetime import UTC, date, datetime

import httpx
import pytest
import respx
from sqlalchemy import select

from app.core.db import make_engine, make_session_factory
from app.core.models import Alert, Base, Company, Job, JobAnalysis, JobUserState, Setting
from app.core.models import TagHistory as TH
from app.core.tags import set_tag
from app.notify.alerts import process_new, refresh_after_analysis
from app.notify.buttons import OFFSET_KEY
from app.notify.telegram import TelegramChannel
from app.worker.poller import poll_forever, poll_once
from app.worker.runner import Ctx

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
API = "https://api.telegram.org/botTOKEN"
CHAT = 42


@pytest.fixture
def sf(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(eng)
    return make_session_factory(eng)


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
        m.answer = m.post(f"{API}/answerCallbackQuery").mock(
            return_value=httpx.Response(200, json={"ok": True, "result": True})
        )
        m.updates = m.post(f"{API}/getUpdates")
        yield m


@pytest.fixture
def channel():
    return TelegramChannel("TOKEN", str(CHAT), httpx.AsyncClient())


@pytest.fixture
def ctx(sf, channel):
    return Ctx(
        settings=None,
        session_factory=sf,
        client=None,
        provider=None,
        pacer=None,
        channel=channel,
        keywords=None,
    )


def seed(sf, n=1):
    """A loaded source with n open tech internships. Returns (source_id, [job_id])."""
    from app.core.models import Source  # noqa: PLC0415

    with sf() as s:
        c = Company(slug="google", name="Google")
        s.add(c)
        s.flush()
        src = Source(company_id=c.id, key="google", adapter="google", initial_load_done=True)
        s.add(src)
        s.flush()
        ids = []
        for i in range(n):
            j = Job(
                company_id=c.id,
                source_ids=[src.id],
                external_id=str(i),
                url=f"https://x/{i}",
                title=f"Software Intern {i}",
                locations=["Bengaluru, India"],
                content_hash="h",
                is_internship=True,
                is_tech=True,
                first_seen_at=T0,
                last_seen_at=T0,
            )
            s.add(j)
            s.flush()
            ids.append(j.id)
        s.commit()
        return src.id, ids


async def alert(sf, channel, n=1):
    from app.core.models import Source  # noqa: PLC0415

    sid, ids = seed(sf, n)
    with sf() as s:
        await process_new(s, channel, s.get(Source, sid), ids, T0)
        s.commit()
    return ids


def body(call):
    return json.loads(call.request.content)


def buttons(payload):
    return [(b["text"], b["callback_data"]) for b in payload["reply_markup"]["inline_keyboard"][0]]


def press(update_id, data, chat=CHAT, message_id=1):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "from": {"id": chat},
            "data": data,
            "message": {"message_id": message_id, "chat": {"id": chat, "type": "private"}},
        },
    }


def updates(*items):
    return httpx.Response(200, json={"ok": True, "result": list(items)})


def tag_of(sf, job_id):
    with sf() as s:
        us = s.get(JobUserState, job_id)
        return us.tag if us else None


def history(sf, job_id):
    with sf() as s:
        return [
            (h.from_tag, h.to_tag, h.event_date)
            for h in s.scalars(select(TH).where(TH.job_id == job_id).order_by(TH.id))
        ]


# --- sending -------------------------------------------------------------------------


async def test_single_alert_has_three_tag_buttons(sf, tg, channel):
    [j] = await alert(sf, channel)
    assert buttons(body(tg.send.calls.last)) == [
        ("❤️ Like", f"t:{j}:l"),
        ("✅ Applied", f"t:{j}:a"),
        ("🗑 Dismiss", f"t:{j}:d"),
    ]


async def test_grouped_burst_has_no_buttons(sf, tg, channel):
    await alert(sf, channel, n=11)
    assert tg.send.call_count == 1 and "reply_markup" not in body(tg.send.calls.last)


async def test_first_run_summary_has_no_buttons(sf, tg, channel):
    from app.core.models import Source  # noqa: PLC0415

    sid, ids = seed(sf, 3)
    with sf() as s:
        src = s.get(Source, sid)
        src.initial_load_done = False
        await process_new(s, channel, src, ids, T0)
    assert tg.send.call_count == 1 and "reply_markup" not in body(tg.send.calls.last)


# --- pressing ------------------------------------------------------------------------


async def test_like_press_tags_answers_and_edits(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.updates.mock(return_value=updates(press(100, f"t:{j}:l")))
    assert await poll_once(ctx, now=T0) == 1
    assert tag_of(sf, j) == "liked"
    assert history(sf, j) == [(None, "liked", None)]
    assert body(tg.answer.calls.last) == {"callback_query_id": "cb100", "text": "Liked"}
    edit = body(tg.edit.calls.last)
    assert edit["message_id"] == 1 and "Software Intern 0" in edit["text"]
    assert buttons(edit)[0] == ("✓ Liked", f"t:{j}:-")  # pressing again removes it
    assert buttons(edit)[1:] == [("✅ Applied", f"t:{j}:a"), ("🗑 Dismiss", f"t:{j}:d")]


async def test_pressing_the_current_tag_removes_it(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.updates.mock(side_effect=[updates(press(1, f"t:{j}:l")), updates(press(2, f"t:{j}:-"))])
    await poll_once(ctx, now=T0)
    await poll_once(ctx, now=T0)
    assert tag_of(sf, j) is None
    assert history(sf, j) == [(None, "liked", None), ("liked", None, None)]
    assert body(tg.answer.calls.last)["text"] == "Tag removed"
    assert buttons(body(tg.edit.calls.last))[0] == ("❤️ Like", f"t:{j}:l")


async def test_applied_is_dated_today_in_india(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.updates.mock(return_value=updates(press(1, f"t:{j}:a")))
    await poll_once(ctx, now=datetime(2026, 11, 12, 20, 0, tzinfo=UTC))  # 01:30 IST on the 13th
    assert history(sf, j) == [(None, "applied", date(2026, 11, 13))]
    assert body(tg.answer.calls.last)["text"] == "Applied"
    assert buttons(body(tg.edit.calls.last))[1] == ("✓ Applied", f"t:{j}:-")


async def test_dismiss_replaces_like(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.updates.mock(side_effect=[updates(press(1, f"t:{j}:l")), updates(press(2, f"t:{j}:d"))])
    await poll_once(ctx, now=T0)
    await poll_once(ctx, now=T0)
    assert tag_of(sf, j) == "dismissed"
    assert [h[:2] for h in history(sf, j)] == [(None, "liked"), ("liked", "dismissed")]
    assert body(tg.answer.calls.last)["text"] == "Dismissed"


async def test_press_from_another_chat_is_ignored(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.updates.mock(return_value=updates(press(7, f"t:{j}:l", chat=999)))
    await poll_once(ctx, now=T0)
    assert tag_of(sf, j) is None and history(sf, j) == []
    assert tg.answer.call_count == 0 and tg.edit.call_count == 0
    with sf() as s:
        assert s.get(Setting, OFFSET_KEY).value == {"offset": 8}  # still moved past it


async def test_any_member_of_the_configured_chat_counts(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    u = press(7, f"t:{j}:l")
    u["callback_query"]["from"]["id"] = 999  # someone else, if the chat were a group
    u["callback_query"]["message"]["chat"]["type"] = "group"
    tg.updates.mock(return_value=updates(u))
    await poll_once(ctx, now=T0)
    assert tag_of(sf, j) == "liked"  # TELEGRAM_CHAT_ID names a chat, not a person


async def test_messages_and_bad_data_are_skipped(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.updates.mock(
        return_value=updates(
            {"update_id": 1, "message": {"chat": {"id": CHAT}, "text": "hi"}},
            press(2, "t:abc:l"),
            press(3, f"t:{j}:x"),
            press(4, "t:99999:l"),
        )
    )
    assert await poll_once(ctx, now=T0) == 4
    assert tag_of(sf, j) is None
    assert [body(c)["text"] for c in tg.answer.calls] == ["Unknown button"] * 2 + ["Job not found"]
    assert tg.edit.call_count == 0


# --- offset --------------------------------------------------------------------------


async def test_offset_is_stored_and_sent_after_a_restart(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.updates.mock(side_effect=[updates(press(100, f"t:{j}:l")), updates()])
    await poll_once(ctx, now=T0)
    restarted = TelegramChannel("TOKEN", str(CHAT), httpx.AsyncClient())
    fresh = Ctx(**{**ctx.__dict__, "channel": restarted})
    await poll_once(fresh, now=T0)
    assert "offset" not in body(tg.updates.calls[0])
    assert body(tg.updates.calls[1])["offset"] == 101
    assert body(tg.updates.calls[1])["allowed_updates"] == ["callback_query"]


async def test_an_update_already_handled_is_not_handled_again(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    with sf() as s:
        s.add(Setting(key=OFFSET_KEY, value={"offset": 101}))
        s.commit()
    tg.updates.mock(return_value=updates(press(100, f"t:{j}:l")))  # Telegram repeats it
    assert await poll_once(ctx, now=T0) == 0
    assert tag_of(sf, j) is None and tg.answer.call_count == 0


async def test_telegram_errors_back_off_and_keep_polling(ctx, tg):
    tg.updates.mock(
        side_effect=[httpx.Response(502), httpx.ConnectError("down"), httpx.Response(502)]
    )
    waits = []

    class Stop(BaseException):
        pass

    async def sleep(s):
        waits.append(s)
        if len(waits) == 3:
            raise Stop

    with pytest.raises(Stop):
        await poll_forever(ctx, sleep=sleep)
    assert waits == [5, 10, 20]


# --- the two edits keep each other's parts ---------------------------------------------


async def test_eligibility_edit_keeps_the_tag_buttons(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.updates.mock(return_value=updates(press(1, f"t:{j}:l")))
    await poll_once(ctx, now=T0)
    assert "🔍 Checking eligibility…" in body(tg.edit.calls.last)["text"]
    with sf() as s:
        s.add(
            JobAnalysis(
                job_id=j,
                model="m",
                prompt_version="1",
                sections={},
                eligibility="ok",
                created_at=T0,
            )
        )
        s.commit()
    with sf() as s:
        await refresh_after_analysis(s, channel, j, T0)
    last = body(tg.edit.calls.last)
    assert "✅ Eligible" in last["text"] and buttons(last)[0] == ("✓ Liked", f"t:{j}:-")


async def test_press_after_eligibility_keeps_the_eligibility_line(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    with sf() as s:
        s.add(
            JobAnalysis(
                job_id=j,
                model="m",
                prompt_version="1",
                sections={},
                eligibility="warn",
                eligibility_quote="US students only",
                created_at=T0,
            )
        )
        s.commit()
    with sf() as s:
        await refresh_after_analysis(s, channel, j, T0)
    assert buttons(body(tg.edit.calls.last))[0] == ("❤️ Like", f"t:{j}:l")
    tg.updates.mock(return_value=updates(press(1, f"t:{j}:d")))
    await poll_once(ctx, now=T0)
    last = body(tg.edit.calls.last)
    assert "⚠️ Check: “US students only”" in last["text"]
    assert buttons(last)[2] == ("✓ Dismissed", f"t:{j}:-")


async def test_tag_set_on_the_dashboard_shows_on_the_next_edit(sf, tg, channel):
    [j] = await alert(sf, channel)
    with sf() as s:
        set_tag(s, j, "applied", T0)
        s.commit()
    with sf() as s:
        await refresh_after_analysis(s, channel, j, T0)
    assert buttons(body(tg.edit.calls.last))[1] == ("✓ Applied", f"t:{j}:-")


async def test_stale_like_button_after_dashboard_like_changes_nothing(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    with sf() as s:
        set_tag(s, j, "liked", T0)  # from the dashboard; the message still shows "Like"
        s.commit()
    tg.updates.mock(return_value=updates(press(1, f"t:{j}:l")))
    await poll_once(ctx, now=T0)
    assert tag_of(sf, j) == "liked" and history(sf, j) == [(None, "liked", None)]
    assert buttons(body(tg.edit.calls.last))[0] == ("✓ Liked", f"t:{j}:-")


async def test_unchanged_message_is_not_an_error(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.edit.mock(
        return_value=httpx.Response(
            400,
            json={
                "ok": False,
                "description": "Bad Request: message is not modified: specified new message "
                "content and reply markup are exactly the same",
            },
        )
    )
    with sf() as s:
        await refresh_after_analysis(s, channel, j, T0)
        alert_row = s.scalars(select(Alert)).one()
        assert alert_row.edited_at == T0


async def test_answer_failing_still_edits(sf, tg, ctx, channel):
    [j] = await alert(sf, channel)
    tg.answer.mock(
        return_value=httpx.Response(
            400, json={"ok": False, "description": "Bad Request: query is too old"}
        )
    )
    tg.updates.mock(return_value=updates(press(1, f"t:{j}:l")))
    await poll_once(ctx, now=T0)
    assert tag_of(sf, j) == "liked" and tg.edit.call_count == 1


async def test_press_during_a_slow_eligibility_edit_ends_with_both(sf, tg, ctx, channel):
    """The eligibility edit is drawn before the press, but Telegram is slow to take it.
    Without the lock, it would land last and wipe the ✓ off the button."""
    import asyncio  # noqa: PLC0415

    [j] = await alert(sf, channel)
    with sf() as s:
        s.add(
            JobAnalysis(
                job_id=j,
                model="m",
                prompt_version="1",
                sections={},
                eligibility="ok",
                created_at=T0,
            )
        )
        s.commit()
    first = {"slow": True}

    async def slow_then_fast(request):
        if first.pop("slow", False):
            await asyncio.sleep(0.1)
        return httpx.Response(200, json={"ok": True, "result": {}})

    tg.edit.mock(side_effect=slow_then_fast)
    tg.updates.mock(return_value=updates(press(1, f"t:{j}:l")))

    async def eligibility():
        with sf() as s:
            await refresh_after_analysis(s, channel, j, T0)

    async def pressed():
        await asyncio.sleep(0.01)  # the eligibility edit is already on its way
        await poll_once(ctx, now=T0)

    await asyncio.gather(eligibility(), pressed())
    last = body(tg.edit.calls.last)
    assert "✅ Eligible" in last["text"] and buttons(last)[0] == ("✓ Liked", f"t:{j}:-")
