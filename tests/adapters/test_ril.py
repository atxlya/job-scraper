from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest

from app.adapters.base import ParseError, RawJob
from app.adapters.company.reliance import RESULTS_URL, RilAdapter
from tests.conftest import load_fixture

DETAIL = (
    "https://careers.ril.com/rilcareers/frmJobSearch.aspx?"
    "JBTITLE=H4q0XLMKMMgn8ATzfCR3nQ==&jbID=/MCeoKnMrIGvezewm68JMQ=="
)


def html(name: str, adapter: str = "ril") -> httpx.Response:
    return httpx.Response(200, content=load_fixture(adapter, name))


def ids(name: str) -> set[str]:
    import re  # noqa: PLC0415

    text = load_fixture("ril", name).decode("utf-8")
    return set(re.findall(r"rgJobs_hylUser_\d+\"[^>]*>[^<]*\(\s*(\d+)\s*\)", text))


@pytest.fixture
def ril(mock):
    seen: list[bytes] = []

    def get(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path)
        return html("results")

    def post(request: httpx.Request) -> httpx.Response:
        body = parse_qs(request.content.decode())
        if body["__EVENTTARGET"] == ["ctl00$MainContent$ddlentries"]:
            return html("results_25")
        name = body["__EVENTTARGET"][0]
        assert name.endswith("PageDropDownList") and body[name] == ["2"]
        return html("results_25_p2")

    mock.get(url__regex=r"https://careers\.ril\.com/rilcareers/frmJobSearch.*").mock(
        side_effect=get
    )
    posts = mock.post(url__regex=r"https://careers\.ril\.com/rilcareers/.*").mock(side_effect=post)
    return seen, posts


async def test_parses_results(client, ril):
    res = await RilAdapter().list_jobs(client, {}, "incremental")
    assert len(res.jobs) == 10 and res.complete is False and res.reported_total is None
    first = res.jobs[0]
    assert first.external_id == "83078441"
    assert first.title == "Const Engr - CHO Projects Civil"
    assert first.locations == ["Jamnagar"] and first.country_codes == ["IN"]
    assert first.posted_at == datetime(2026, 11, 6, tzinfo=UTC)
    assert first.url == DETAIL


async def test_full_pages_with_postbacks(client, ril):
    _, posts = ril
    res = await RilAdapter().list_jobs(client, {}, "full")
    assert posts.call_count == 2
    assert {j.external_id for j in res.jobs} == ids("results_25") | ids("results_25_p2")
    assert len(res.jobs) == 44 and res.complete is True


async def test_results_url_sent_verbatim(client, ril):
    seen, _ = ril
    await RilAdapter().list_jobs(client, {}, "incremental")
    assert b"func=w+cpdiT6wL4=" in seen[0]
    assert seen[0] == RESULTS_URL.removeprefix("https://careers.ril.com").encode()


def job() -> RawJob:
    return RawJob(external_id="83078441", title="Const Engr - CHO Projects Civil", url=DETAIL)


async def test_detail(client, mock):
    mock.get(url__regex=r"https://careers\.ril\.com/rilcareers/frmJobSearch.*").mock(
        return_value=html("detail")
    )
    got = await RilAdapter().fetch_detail(client, {}, job())
    assert "Area grading and land development" in got.description_html


async def test_profile_page_raises_parse_error(client, mock):
    mock.get(url__regex=r"https://careers\.ril\.com/rilcareers/frmJobSearch.*").mock(
        return_value=html("profile_page")
    )
    with pytest.raises(ParseError):
        await RilAdapter().fetch_detail(client, {}, job())


async def test_wrong_page_raises_parse_error(client, mock):
    mock.get(url__regex=r"https://careers\.ril\.com/rilcareers/frmJobSearch.*").mock(
        return_value=html("categories", "jio")
    )
    with pytest.raises(ParseError):
        await RilAdapter().list_jobs(client, {}, "incremental")


async def test_full_without_pages_text_but_pager_raises(client, mock):
    broken = load_fixture("ril", "results").replace(b"Showing 1 of 5 Pages", b"Page 1 of 5")
    mock.get(url__regex=r"https://careers\.ril\.com/rilcareers/frmJobSearch.*").mock(
        return_value=httpx.Response(200, content=broken)
    )
    with pytest.raises(ParseError, match="page count"):
        await RilAdapter().list_jobs(client, {}, "full")
