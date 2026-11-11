import re
from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.rss import RssAdapter
from tests.conftest import load_fixture

URL = "https://careers.zohocorp.com/jobs/Careers/rss"
CFG = {"url": URL}


async def test_parses_feed(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, content=load_fixture("rss", "zoho")))
    res = await RssAdapter().list_jobs(client, CFG, "full")
    assert len(res.jobs) == 9 and res.complete is True and res.reported_total is None
    job = res.jobs[0]
    assert job.external_id == "193779000024446019"
    assert job.title == "Software Developers"
    assert (
        job.url
        == "https://careers.zohocorp.com/jobs/Careers/193779000024446019/Software-Developers"
    )
    assert job.locations == ["Tamil Nadu Tamil Nadu India"]
    assert job.country_codes == ["IN"]
    assert "Design and develop high-volume" in job.description_html
    assert "Category:" not in job.description_html
    assert "Details</a>" not in job.description_html


async def test_title_entities_unescaped(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, content=load_fixture("rss", "zoho")))
    res = await RssAdapter().list_jobs(client, CFG, "full")
    assert res.jobs[1].title == "Content/Technical Writers"


async def test_ist_pubdate(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, content=load_fixture("rss", "zoho")))
    res = await RssAdapter().list_jobs(client, CFG, "full")
    assert res.jobs[0].posted_at == datetime(2022, 6, 24, 6, 30, tzinfo=UTC)


async def test_feed_allowed_by_real_robots(client, mock):
    rules = (
        "User-agent: *\nAllow: /recruit/downloadrssfeed\nAllow: /jobs\n"
        "Allow: /jobs/\nAllow: /jobs/*\nDisallow: /\n"
    )
    mock.get("https://careers.zohocorp.com/robots.txt").mock(
        return_value=httpx.Response(200, text=rules)
    )
    route = mock.get(URL).mock(
        return_value=httpx.Response(200, content=load_fixture("rss", "zoho"))
    )
    res = await RssAdapter().list_jobs(client, CFG, "full")
    assert route.called and len(res.jobs) == 9


async def test_detail_returns_current_item(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, content=load_fixture("rss", "zoho")))
    job = RawJob(external_id="193779000024446019", title="old", url=URL)
    now = await RssAdapter().fetch_detail(client, CFG, job)
    assert now.title == "Software Developers"


async def test_detail_gone_when_not_in_feed(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, content=load_fixture("rss", "zoho")))
    job = RawJob(external_id="999", title="Gone job", url=URL)
    assert await RssAdapter().fetch_detail(client, CFG, job) is GONE


async def test_not_rss_raises_parse_error(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, content=b"<html><body>hi</body></html>"))
    with pytest.raises(ParseError):
        await RssAdapter().list_jobs(client, CFG, "full")
    mock.get(URL).mock(return_value=httpx.Response(200, content=b"not xml at all"))
    with pytest.raises(ParseError):
        await RssAdapter().list_jobs(client, CFG, "full")


def feed(*swaps: tuple[bytes, bytes]) -> httpx.Response:
    """The recorded feed with exact byte swaps (each must apply)."""
    body = load_fixture("rss", "zoho")
    for old, new in swaps:
        assert old in body
        body = body.replace(old, new, 1)
    return httpx.Response(200, content=body)


FIRST_TITLE = b"<title>Software Developers</title>"


async def test_item_without_title_is_skipped_and_run_not_complete(client, mock):
    mock.get(URL).mock(return_value=feed((FIRST_TITLE, b"<title></title>")))
    res = await RssAdapter().list_jobs(client, CFG, "full")
    assert len(res.jobs) == 8 and res.complete is False


async def test_feed_with_only_bad_items_raises(client, mock):
    body = re.sub(
        rb"<title>[^<]*</title>\s*<link>", b"<title></title><link>", load_fixture("rss", "zoho")
    )
    mock.get(URL).mock(return_value=httpx.Response(200, content=body))
    with pytest.raises(ParseError, match="every item"):
        await RssAdapter().list_jobs(client, CFG, "full")


async def test_detail_not_gone_while_items_are_skipped(client, mock):
    mock.get(URL).mock(return_value=feed((FIRST_TITLE, b"<title></title>")))
    job = RawJob(external_id="999", title="Gone job", url=URL)
    with pytest.raises(ParseError, match="skipped"):
        await RssAdapter().fetch_detail(client, CFG, job)


async def test_guid_falls_back_to_link(client, mock):
    guid = b'<guid isPermaLink="false">193779000024446019</guid>'
    mock.get(URL).mock(return_value=feed((guid, b"")))
    res = await RssAdapter().list_jobs(client, CFG, "full")
    assert res.jobs[0].external_id == (
        "https://careers.zohocorp.com/jobs/Careers/193779000024446019/Software-Developers"
    )


def test_pubdate_other_zone_and_unreadable():
    from app.adapters.rss import _posted  # noqa: PLC0415

    assert _posted("Tue, 10 Nov 2026 08:00:00 GMT") == datetime(2026, 11, 10, 8, tzinfo=UTC)
    assert _posted("Tue, 10 Nov 2026 08:00:00 +0100") == datetime(2026, 11, 10, 7, tzinfo=UTC)
    assert _posted("sometime last week") is None
    assert _posted("") is None


async def test_detail_reads_feed_once_per_run(client, mock):
    route = mock.get(URL).mock(
        return_value=httpx.Response(200, content=load_fixture("rss", "zoho"))
    )
    adapter = RssAdapter()
    for key in ("193779000024446019", "999"):
        await adapter.fetch_detail(client, CFG, RawJob(external_id=key, title="t", url=URL))
    assert route.call_count == 1
