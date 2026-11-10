import json

import httpx
import pytest
import respx

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.oracle_hcm import OracleHcmAdapter
from app.http.client import PoliteClient
from tests.conftest import load_fixture

HOST = "eeho.fa.us2.oraclecloud.com"
CFG = {"host": HOST, "site": "CX_45001"}
LIST = f"https://{HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
DETAIL = f"https://{HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"


def fx(name):
    return json.loads(load_fixture("oracle_hcm", name))


@pytest.fixture
def client():
    async def nosleep(_s):
        return None

    return PoliteClient(min_interval_s=0, sleep=nosleep)


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        m.get(url__regex=r"https://[^/]+/robots\.txt").mock(return_value=httpx.Response(404))
        yield m


def offsets(route):
    out = []
    for c in route.calls:
        finder = c.request.url.params["finder"]
        out.append(int(finder.split("offset=")[1].split(",")[0]))
    return out


async def test_parses_listing(client, mock):
    page = fx("oracle_page1")
    mock.get(LIST).mock(return_value=httpx.Response(200, json=page))
    res = await OracleHcmAdapter().list_jobs(client, CFG, "incremental")
    reqs = page["items"][0]["requisitionList"]
    assert len(res.jobs) == len(reqs)
    j = res.jobs[0]
    assert j.external_id == reqs[0]["Id"]
    assert (
        j.url == f"https://{HOST}/hcmUI/CandidateExperience/en/sites/CX_45001/job/{reqs[0]['Id']}"
    )
    assert j.posted_at is not None and j.posted_at.date().isoformat() == reqs[0]["PostedDate"]
    assert j.country_codes == [reqs[0]["PrimaryLocationCountry"]]
    assert res.reported_total == int(page["items"][0]["TotalJobsCount"])


async def test_paginates_until_total(client, mock):
    p1, p2 = fx("oracle_page1"), fx("oracle_page2")
    p1["items"][0]["TotalJobsCount"] = 50  # two real pages are the whole listing

    def respond(request):
        return httpx.Response(200, json=p1 if offsets_of(request) == 0 else p2)

    def offsets_of(request):
        return int(request.url.params["finder"].split("offset=")[1].split(",")[0])

    route = mock.get(LIST).mock(side_effect=respond)
    res = await OracleHcmAdapter().list_jobs(client, CFG, "full")
    assert offsets(route) == [0, 25]
    assert res.complete is True


async def test_sorted_newest_first(client, mock):
    route = mock.get(LIST).mock(return_value=httpx.Response(200, json=fx("oracle_page1")))
    await OracleHcmAdapter().list_jobs(client, CFG, "incremental")
    assert "sortBy=POSTING_DATES_DESC" in route.calls.last.request.url.params["finder"]


async def test_incremental_reads_first_pages_only(client, mock):
    route = mock.get(LIST).mock(return_value=httpx.Response(200, json=fx("oracle_page1")))
    res = await OracleHcmAdapter().list_jobs(client, CFG, "incremental")
    assert route.call_count <= 3
    assert res.complete is False


async def test_detail_fills_description(client, mock):
    mock.get(DETAIL).mock(return_value=httpx.Response(200, json=fx("oracle_detail")))
    job = RawJob(external_id="347942", title="t", url="u")
    out = await OracleHcmAdapter().fetch_detail(client, CFG, job)
    assert out.description_html and "What You" in out.description_html
    assert out.posted_at is not None and out.posted_at.isoformat().startswith("2026-11-09T03:09")


async def test_detail_not_found_is_gone(client, mock):
    mock.get(DETAIL).mock(return_value=httpx.Response(200, json=fx("oracle_detail_missing")))
    job = RawJob(external_id="9999999999", title="t", url="u")
    assert await OracleHcmAdapter().fetch_detail(client, CFG, job) is GONE


async def test_unexpected_shape_raises_parse_error(client, mock):
    mock.get(LIST).mock(return_value=httpx.Response(200, json={"items": []}))
    with pytest.raises(ParseError):
        await OracleHcmAdapter().list_jobs(client, CFG, "full")
