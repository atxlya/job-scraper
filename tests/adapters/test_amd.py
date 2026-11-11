from datetime import UTC, datetime

import httpx

from app.adapters.company import amd
from app.adapters.company.amd import URL, AmdAdapter
from tests.conftest import load_json

CFG = {"intern_category": "Student / Intern / Temp"}


async def test_parses_listing(client, mock):
    body = load_json("amd", "all_p1")
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    res = await AmdAdapter().list_jobs(client, CFG, "incremental")
    d = body["jobs"][0]["data"]
    j = res.jobs[0]
    assert j.external_id == d["req_id"] and j.title == d["title"]
    assert j.url == d["meta_data"]["canonical_url"] and j.apply_url == d["apply_url"]
    assert j.locations == [d["full_location"]]
    assert d["country_code"] in j.country_codes
    assert j.posted_at == datetime.strptime(d["posted_date"], "%Y-%m-%dT%H:%M:%S%z")
    assert j.posted_at.tzinfo is not None and j.posted_at.utcoffset().total_seconds() == 0
    assert j.description_html and res.reported_total == body["totalCount"]


async def test_intern_category_sets_flag(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, json=load_json("amd", "interns")))
    res = await AmdAdapter().list_jobs(client, CFG, "incremental")
    assert res.jobs and all(j.platform_flags == {"intern": True} for j in res.jobs)
    assert res.jobs[0].posted_at.tzinfo == UTC


async def test_incremental_filters_category(client, mock):
    route = mock.get(URL).mock(return_value=httpx.Response(200, json=load_json("amd", "interns")))
    res = await AmdAdapter().list_jobs(client, CFG, "incremental")
    assert len(route.calls) == 1 and res.complete is False
    assert route.calls.last.request.url.params["categories"] == "Student / Intern / Temp"


async def test_full_pages_until_total(client, mock, monkeypatch):
    monkeypatch.setattr(amd, "PAGE", 8)
    body = load_json("amd", "all_p1")
    body["totalCount"] = 20
    route = mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    res = await AmdAdapter().list_jobs(client, CFG, "full")
    assert [int(c.request.url.params["page"]) for c in route.calls] == [1, 2, 3]
    assert "categories" not in route.calls.last.request.url.params
    assert res.complete is True


async def test_empty_last_page_not_complete(client, mock, monkeypatch):
    monkeypatch.setattr(amd, "PAGE", 8)
    body = load_json("amd", "all_p1")
    body["totalCount"] = 20
    empty = {**body, "jobs": []}

    def respond(request):
        last = request.url.params["page"] == "3"  # the final page comes back empty
        return httpx.Response(200, json=empty if last else body)

    mock.get(URL).mock(side_effect=respond)
    assert (await AmdAdapter().list_jobs(client, CFG, "full")).complete is False
