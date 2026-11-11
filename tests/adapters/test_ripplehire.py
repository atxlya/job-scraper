import json
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest

from app.adapters.base import ParseError, RawJob
from app.adapters.ripplehire import RippleHireAdapter
from tests.conftest import load_fixture, load_json

CFG = {"host": "ltm.ripplehire.com", "token": "xviyQvbnyYZdGtozXoNm", "geo": "India"}
SEARCH = "https://ltm.ripplehire.com/candidate/candidatejobsearch"
DETAIL = "https://ltm.ripplehire.com/candidate/candidatejobdetail"


def params_of(call) -> dict:
    return json.loads(parse_qs(call.request.content.decode())["careerSiteUrlParams"][0])


def by_page(pages: dict[int, object]):
    def answer(request: httpx.Request) -> httpx.Response:
        page = json.loads(parse_qs(request.content.decode())["careerSiteUrlParams"][0])["page"]
        return httpx.Response(200, json=pages[page])

    return answer


async def test_parses_search(client, mock):
    route = mock.post(SEARCH).mock(
        return_value=httpx.Response(200, json=load_json("ripplehire", "search"))
    )
    res = await RippleHireAdapter().list_jobs(client, CFG, "incremental")
    assert res.reported_total == 620
    first = res.jobs[0]
    assert first.external_id == "907181"
    assert first.title == "Senior Specialist - Architecture"
    assert first.locations == ["Bengaluru"]
    assert first.country_codes == ["IN"]
    assert first.url.endswith("#detail/job/907181")
    assert first.url.startswith("https://ltm.ripplehire.com/candidate/?token=xviyQvbnyYZdGtozXoNm")
    sent = params_of(route.calls[0])
    assert sent["token"] == CFG["token"] and sent["geo"] == "India" and sent["page"] == 0
    assert parse_qs(route.calls[0].request.content.decode())["lang"] == ["en"]


async def test_full_stops_when_total_reached(client, mock):
    data = load_json("ripplehire", "search")
    data["totalJobCount"] = len(data["jobVoList"])
    route = mock.post(SEARCH).mock(return_value=httpx.Response(200, json=data))
    res = await RippleHireAdapter().list_jobs(client, CFG, "full")
    assert route.call_count == 1
    assert res.complete is True


async def test_full_stops_on_empty_page(client, mock):
    route = mock.post(SEARCH).mock(
        side_effect=by_page(
            {0: load_json("ripplehire", "search"), 1: load_json("ripplehire", "search_beyond")}
        )
    )
    res = await RippleHireAdapter().list_jobs(client, CFG, "full")
    assert [params_of(c)["page"] for c in route.calls] == [0, 1]
    assert res.complete is False
    assert len(res.jobs) == len(load_json("ripplehire", "search")["jobVoList"])


async def test_incremental_reads_page_zero(client, mock):
    route = mock.post(SEARCH).mock(
        return_value=httpx.Response(200, json=load_json("ripplehire", "search"))
    )
    res = await RippleHireAdapter().list_jobs(client, CFG, "incremental")
    assert route.call_count == 1 and res.complete is False


def job() -> RawJob:
    return RawJob(external_id="907181", title="Senior Specialist - Architecture", url="https://x")


async def test_detail(client, mock):
    route = mock.get(DETAIL).mock(
        return_value=httpx.Response(200, content=load_fixture("ripplehire", "detail"))
    )
    got = await RippleHireAdapter().fetch_detail(client, CFG, job())
    assert "Full Stack Developer" in got.description_html
    assert "Java, React" in got.description_html
    assert got.posted_at == datetime(2026, 11, 9, tzinfo=UTC)
    assert got.employment_type == "Permanent"
    q = route.calls[0].request.url.params
    assert q["jobSeq"] == "907181" and q["token"] == CFG["token"] and q["source"] == "CAREERSITE"


async def test_detail_500_is_error_not_gone(client, mock):
    mock.get(DETAIL).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):  # raised, so never GONE
        await RippleHireAdapter().fetch_detail(client, CFG, job())


async def test_html_answer_raises_parse_error(client, mock):
    mock.post(SEARCH).mock(return_value=httpx.Response(200, text="<html>login</html>"))
    with pytest.raises(ParseError):
        await RippleHireAdapter().list_jobs(client, CFG, "incremental")
