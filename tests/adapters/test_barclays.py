import json

import httpx
import pytest
import respx

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.company.barclays import BarclaysAdapter
from app.http.client import PoliteClient
from tests.conftest import load_fixture

BASE = "https://search.jobs.barclays"
CFG = {"base": BASE, "org_id": 13015}
JOB_URL = f"{BASE}/job/chennai/liquidity-risk-reporting-analyst/13015/102599897824"


@pytest.fixture
def client():
    async def nosleep(_s):
        return None

    return PoliteClient(min_interval_s=0, sleep=nosleep)


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        m.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\n"))
        yield m


def results():
    return json.loads(load_fixture("barclays", "results_page1"))


async def test_barclays_parses_cards(client, mock):
    page = results()
    mock.get(f"{BASE}/search-jobs/results").mock(return_value=httpx.Response(200, json=page))
    res = await BarclaysAdapter().list_jobs(client, CFG, "incremental")
    assert len(res.jobs) == 100  # RecordsPerPage=100 on the recorded page
    j = next(j for j in res.jobs if j.external_id == "102599897824")
    assert j.title == "Liquidity Risk Reporting - Analyst"
    assert j.url == JOB_URL
    assert j.locations == ["Chennai, India", "Noida, India"]
    assert j.country_codes == ["IN"]
    assert j.posted_at is None  # card date "09 Nov" has no year and is never parsed
    assert res.reported_total == 609


async def test_barclays_full_reads_all_pages(client, mock):
    page = results()
    route = mock.get(f"{BASE}/search-jobs/results").mock(
        return_value=httpx.Response(200, json=page)
    )
    res = await BarclaysAdapter().list_jobs(client, CFG, "full")
    pages = [int(c.request.url.params["CurrentPage"]) for c in route.calls]
    assert pages == [1, 2, 3, 4, 5, 6, 7]  # data-total-pages="7"
    assert res.complete is True
    assert all(c.request.url.params["RecordsPerPage"] == "100" for c in route.calls)


async def test_barclays_detail_jsonld_date(client, mock):
    mock.get(JOB_URL).mock(
        return_value=httpx.Response(
            200, content=load_fixture("barclays", "job_page"), headers={"content-type": "text/html"}
        )
    )
    job = RawJob(external_id="102599897824", title="t", url=JOB_URL)
    out = await BarclaysAdapter().fetch_detail(client, CFG, job)
    assert out.posted_at is not None and out.posted_at.isoformat() == "2026-11-10T00:00:00+00:00"
    assert out.description_html and "Liquidity" in out.description_html
    assert out.employment_type == "Permanent"
    assert out.apply_url and out.apply_url.endswith("/apply")


async def test_barclays_404_gone(client, mock):
    url = f"{BASE}/job/chennai/not-a-job/13015/1"
    mock.get(url).mock(
        return_value=httpx.Response(
            404,
            content=load_fixture("barclays", "job_missing"),
            headers={"content-type": "text/html"},
        )
    )
    assert (
        await BarclaysAdapter().fetch_detail(
            client, CFG, RawJob(external_id="1", title="t", url=url)
        )
        is GONE
    )


async def test_barclays_bad_shape(client, mock):
    mock.get(f"{BASE}/search-jobs/results").mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(ParseError):
        await BarclaysAdapter().list_jobs(client, CFG, "full")
