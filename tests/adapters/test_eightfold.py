import json

import httpx
import pytest
import respx

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.eightfold import EightfoldAdapter
from app.http.client import PoliteClient
from tests.conftest import load_fixture

CFG = {"host": "jobs.nvidia.com", "domain": "nvidia.com"}
SEARCH = "https://jobs.nvidia.com/api/pcsx/search"
DETAIL = "https://jobs.nvidia.com/api/pcsx/position_details"


def fx(name):
    return json.loads(load_fixture("eightfold", name))


@pytest.fixture
def client():
    async def nosleep(_s):
        return None

    return PoliteClient(min_interval_s=0, sleep=nosleep)


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        m.get(url__regex=r"https://[^/]+/robots\.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
        )
        yield m


def starts(route):
    return [int(c.request.url.params["start"]) for c in route.calls]


async def test_parses_listing(client, mock):
    page1 = fx("nvidia_page1")
    mock.get(SEARCH).mock(return_value=httpx.Response(200, json=page1))
    res = await EightfoldAdapter().list_jobs(client, CFG, "incremental")
    positions = page1["data"]["positions"]
    assert len(res.jobs) == len(positions)
    first = res.jobs[0]
    assert first.external_id == positions[0]["displayJobId"]
    assert first.url == "https://jobs.nvidia.com/careers/job/" + str(positions[0]["id"])
    assert first.posted_at is not None and first.posted_at.tzinfo is not None
    assert first.remote_type == "onsite"
    assert res.reported_total == page1["data"]["count"]


async def test_paginates_until_total(client, mock):
    page1, page2 = fx("nvidia_page1"), fx("nvidia_page2")
    page1["data"]["count"] = 20  # real pages; count lowered so two pages are everything

    def respond(request):
        return httpx.Response(200, json=page1 if request.url.params["start"] == "0" else page2)

    route = mock.get(SEARCH).mock(side_effect=respond)
    res = await EightfoldAdapter().list_jobs(client, CFG, "full")
    assert starts(route) == [0, 10]
    assert res.complete is True


async def test_incremental_reads_first_pages_only(client, mock):
    route = mock.get(SEARCH).mock(return_value=httpx.Response(200, json=fx("nvidia_page1")))
    res = await EightfoldAdapter().list_jobs(client, CFG, "incremental")
    assert route.call_count <= 3
    assert res.complete is False


async def test_filters_passed_through(client, mock):
    route = mock.get(SEARCH).mock(return_value=httpx.Response(200, json=fx("nvidia_page1")))
    cfg = {**CFG, "filters": {"filter_job_category": "univ employment"}}
    await EightfoldAdapter().list_jobs(client, cfg, "incremental")
    params = route.calls.last.request.url.params
    assert params["filter_job_category"] == "univ employment"
    assert params["sort_by"] == "timestamp"


async def test_detail_fills_description(client, mock):
    mock.get(DETAIL).mock(return_value=httpx.Response(200, json=fx("nvidia_detail")))
    job = RawJob(
        external_id="JR2029372", title="t", url="https://jobs.nvidia.com/careers/job/893398640580"
    )
    out = await EightfoldAdapter().fetch_detail(client, CFG, job)
    assert out.description_html and "NVIDIA" in out.description_html
    assert out.apply_url and "myworkdayjobs.com" in out.apply_url
    assert out.employment_type == "Full time"


async def test_detail_not_found_is_gone(client, mock):
    mock.get(DETAIL).mock(return_value=httpx.Response(404, json=fx("nvidia_detail_missing")))
    job = RawJob(external_id="X", title="t", url="https://jobs.nvidia.com/careers/job/1")
    assert await EightfoldAdapter().fetch_detail(client, CFG, job) is GONE


async def test_unexpected_shape_raises_parse_error(client, mock):
    mock.get(SEARCH).mock(return_value=httpx.Response(200, json={"status": 200, "data": {}}))
    with pytest.raises(ParseError):
        await EightfoldAdapter().list_jobs(client, CFG, "full")


async def test_apply_v2_mode_for_hsbc(client, mock):
    url = "https://portal.careers.hsbc.com/api/apply/v2/jobs"
    page = fx("hsbc_v2_page1")
    route = mock.get(url).mock(return_value=httpx.Response(200, json=page))
    cfg = {"host": "portal.careers.hsbc.com", "domain": "hsbc.com", "api": "apply_v2"}
    res = await EightfoldAdapter().list_jobs(client, cfg, "incremental")
    assert route.calls.last.request.url.params["num"] == "10"
    assert res.jobs[0].external_id == page["positions"][0]["display_job_id"]
    assert res.jobs[0].url == page["positions"][0]["canonicalPositionUrl"]
    assert "IN" in res.jobs[0].country_codes


async def test_apply_v2_detail(client, mock):
    mock.get("https://portal.careers.hsbc.com/api/apply/v2/jobs/563774612097430").mock(
        return_value=httpx.Response(200, json=fx("hsbc_v2_detail"))
    )
    cfg = {"host": "portal.careers.hsbc.com", "domain": "hsbc.com", "api": "apply_v2"}
    job = RawJob(
        external_id="55592",
        title="t",
        url="https://portal.careers.hsbc.com/careers/job/563774612097430",
    )
    out = await EightfoldAdapter().fetch_detail(client, cfg, job)
    assert out.description_html and out.description_html.startswith("<div")


async def test_incremental_filters_only_in_incremental(client, mock):
    page1 = fx("nvidia_page1")
    page1["data"]["count"] = 10
    route = mock.get(SEARCH).mock(return_value=httpx.Response(200, json=page1))
    cfg = {**CFG, "incremental_filters": {"query": "intern"}}
    await EightfoldAdapter().list_jobs(client, cfg, "incremental")
    assert route.calls.last.request.url.params["query"] == "intern"
    await EightfoldAdapter().list_jobs(client, cfg, "full")
    assert route.calls.last.request.url.params["query"] == ""
