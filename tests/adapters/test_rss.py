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
