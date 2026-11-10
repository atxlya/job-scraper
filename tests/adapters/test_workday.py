import json

import httpx
import pytest
import respx

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.workday import WorkdayAdapter
from app.http.client import PoliteClient
from tests.conftest import load_fixture

HOST = "visa.wd5.myworkdayjobs.com"
CFG = {"host": HOST, "tenant": "visa", "site": "Visa"}
LIST_URL = f"https://{HOST}/wday/cxs/visa/Visa/jobs"


def fx(name: str) -> dict:
    return json.loads(load_fixture("workday", name))


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


def bodies(route) -> list[dict]:
    return [json.loads(c.request.content) for c in route.calls]


async def test_parses_listing(client, mock):
    page1 = fx("visa_page1")
    mock.post(LIST_URL).mock(return_value=httpx.Response(200, json=page1))
    res = await WorkdayAdapter().list_jobs(client, CFG, "incremental")
    assert len(res.jobs) == len(page1["jobPostings"])
    for j in res.jobs:
        assert j.external_id and j.title and j.url.startswith(f"https://{HOST}/Visa/job/")
    assert res.reported_total == page1["total"]


async def test_paginates_until_total(client, mock):
    page1, page2 = fx("visa_page1"), fx("visa_page2")
    page1["total"] = 40  # real pages; total lowered so two pages are the whole listing

    def respond(request):
        offset = json.loads(request.content)["offset"]
        return httpx.Response(200, json=page1 if offset == 0 else page2)

    route = mock.post(LIST_URL).mock(side_effect=respond)
    res = await WorkdayAdapter().list_jobs(client, CFG, "full")
    assert [b["offset"] for b in bodies(route)] == [0, 20]
    assert res.complete is True
    assert res.reported_total == 40  # page 2 reports total 0; page 1's total is kept


async def test_incremental_reads_first_pages_only(client, mock):
    page1 = fx("visa_page1")
    route = mock.post(LIST_URL).mock(return_value=httpx.Response(200, json=page1))
    res = await WorkdayAdapter().list_jobs(client, CFG, "incremental")
    assert route.call_count <= 3
    assert res.complete is False


async def test_intern_facets_applied_incremental(client, mock):
    facets = {"jobFamily": ["abc123"]}
    route = mock.post(LIST_URL).mock(return_value=httpx.Response(200, json=fx("visa_page1")))
    await WorkdayAdapter().list_jobs(client, {**CFG, "intern_facets": facets}, "incremental")
    assert all(b["appliedFacets"] == facets for b in bodies(route))


async def test_total_cap_splits_by_facet(client, mock):
    capped = fx("accenture_page1")
    assert capped["total"] == 2000
    countries = next(
        v
        for f in capped["facets"]
        if f["facetParameter"] == "locationMainGroup"
        for v in f["values"]
        if v.get("facetParameter") == "locationCountry"
    )["values"]
    small = fx("visa_page1")
    small["total"] = 20

    def respond(request):
        applied = json.loads(request.content)["appliedFacets"]
        return httpx.Response(200, json=small if applied else capped)

    url = "https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs"
    route = mock.post(url).mock(side_effect=respond)
    cfg = {
        "host": "accenture.wd103.myworkdayjobs.com",
        "tenant": "accenture",
        "site": "AccentureCareers",
        "split_facets": ["locationCountry"],
    }
    res = await WorkdayAdapter().list_jobs(client, cfg, "full")
    split_calls = [b for b in bodies(route) if b["appliedFacets"]]
    assert len(split_calls) == len(countries)
    assert len(res.jobs) == len({j.external_id for j in res.jobs}) == 20
    assert res.complete is True


async def test_detail_fills_description(client, mock):
    detail = fx("visa_detail")
    path = detail["jobPostingInfo"]["externalUrl"].split("/Visa", 1)[1]
    mock.get(f"https://{HOST}/wday/cxs/visa/Visa{path}").mock(
        return_value=httpx.Response(200, json=detail)
    )
    job = RawJob(external_id="REF090191W", title="Sr. Director", url=f"https://{HOST}/Visa{path}")
    out = await WorkdayAdapter().fetch_detail(client, CFG, job)
    assert out.description_html and "Visa" in out.description_html
    assert out.posted_at is not None and out.posted_at.date().isoformat() == "2026-11-10"
    assert out.external_id == "REF090191W"
    assert "US" in out.country_codes


async def test_detail_not_found_is_gone(client, mock):
    mock.get(url__regex=rf"https://{HOST}/wday/cxs/visa/Visa/job/.*").mock(
        return_value=httpx.Response(404, json=fx("visa_detail_missing"))
    )
    job = RawJob(external_id="X", title="t", url=f"https://{HOST}/Visa/job/US/Gone_X")
    assert await WorkdayAdapter().fetch_detail(client, CFG, job) is GONE


async def test_unexpected_shape_raises_parse_error(client, mock):
    mock.post(LIST_URL).mock(
        return_value=httpx.Response(
            200, text="<html>Maintenance</html>", headers={"content-type": "text/html"}
        )
    )
    with pytest.raises(ParseError):
        await WorkdayAdapter().list_jobs(client, CFG, "full")


async def test_incomplete_postings_skipped(client, mock):
    page = fx("visa_page1")
    # Shape seen live on Accenture: some postings carry only bulletFields.
    page["jobPostings"][0] = {"bulletFields": ["R00351141", "Bratislava"]}
    page["jobPostings"][1] = {"bulletFields": ["R00358078", "Amsterdam"]}
    mock.post(LIST_URL).mock(return_value=httpx.Response(200, json=page))
    res = await WorkdayAdapter().list_jobs(client, CFG, "incremental")
    assert len(res.jobs) == len(page["jobPostings"]) - 2


async def test_all_postings_incomplete_is_parse_error(client, mock):
    page = fx("visa_page1")
    page["jobPostings"] = [{"bulletFields": ["X"]} for _ in page["jobPostings"]]
    mock.post(LIST_URL).mock(return_value=httpx.Response(200, json=page))
    with pytest.raises(ParseError):
        await WorkdayAdapter().list_jobs(client, CFG, "incremental")
