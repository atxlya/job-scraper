from datetime import UTC, datetime

import httpx
import pytest

from app.adapters import base
from app.adapters.company import amazon
from app.adapters.company.amazon import SEARCH, AmazonAdapter
from app.worker.runner import _mismatch
from tests.conftest import load_json

CFG = {"queries": [{"base_query": "intern"}, {"normalized_country_code[]": "IND"}]}


def serve(mock, intern, india):
    def respond(request):
        q = request.url.params
        return httpx.Response(200, json=intern if "base_query" in q else india)

    return mock.get(SEARCH).mock(side_effect=respond)


def offsets(route, key):
    return [int(c.request.url.params["offset"]) for c in route.calls if key in c.request.url.params]


async def test_parses_listing(client, mock):
    india = load_json("amazon", "india_page1")
    serve(mock, load_json("amazon", "intern_page1"), india)
    res = await AmazonAdapter().list_jobs(client, CFG, "incremental")
    p = india["jobs"][0]
    j = next(j for j in res.jobs if j.external_id == p["id_icims"])
    assert j.title == p["title"].strip()
    assert j.url == "https://www.amazon.jobs" + p["job_path"]
    assert j.apply_url == p["url_next_step"]
    assert j.country_codes == ["IN"]
    assert j.locations == ["Telangana, IND"]
    assert j.posted_at == datetime(2026, 11, 10, tzinfo=UTC)
    assert j.employment_type == p["job_schedule_type"]
    assert j.description_html.startswith(p["description"][:40])
    assert "<h3>Basic qualifications</h3>" in j.description_html


async def test_pages_until_hits(client, mock, monkeypatch):
    monkeypatch.setattr(amazon, "PAGE", 25)
    intern, india = load_json("amazon", "intern_page1"), load_json("amazon", "india_page1")
    intern["hits"] = india["hits"] = 60
    route = serve(mock, intern, india)
    res = await AmazonAdapter().list_jobs(client, CFG, "full")
    assert offsets(route, "base_query") == [0, 25, 50]
    assert offsets(route, "normalized_country_code[]") == [0, 25, 50]
    assert res.complete is True


async def test_overlapping_queries_count_duplicates_once(client, mock):
    india = load_json("amazon", "india_page1")
    india["hits"] = len(india["jobs"])
    serve(mock, india, india)
    res = await AmazonAdapter().list_jobs(client, CFG, "full")
    assert res.reported_total == len(res.jobs) == len(india["jobs"])
    assert not _mismatch(len(res.jobs), res.reported_total)


async def test_hits_cap_not_complete(client, mock):
    intern, india = load_json("amazon", "intern_page1"), load_json("amazon", "india_page1")
    intern["hits"] = 10000
    india["hits"] = len(india["jobs"])
    route = serve(mock, intern, india)
    res = await AmazonAdapter().list_jobs(client, CFG, "full")
    assert res.complete is False
    assert len(route.calls) == 2  # a capped query isn't paged


async def test_incremental_reads_page_one(client, mock):
    route = serve(mock, load_json("amazon", "intern_page1"), load_json("amazon", "india_page1"))
    res = await AmazonAdapter().list_jobs(client, CFG, "incremental")
    assert len(route.calls) == 2 and res.complete is False
    assert all(c.request.url.params["sort"] == "recent" for c in route.calls)


async def test_error_field_raises_parse_error(client, mock):
    bad = load_json("amazon", "india_page1")
    bad["error"] = "search unavailable"
    serve(mock, bad, bad)
    with pytest.raises(base.ParseError):
        await AmazonAdapter().list_jobs(client, CFG, "full")


async def test_detail_makes_no_request(client, mock):
    route = serve(mock, {}, {})
    job = base.RawJob(external_id="1", title="x", url="https://www.amazon.jobs/en/jobs/1")
    assert await AmazonAdapter().fetch_detail(client, CFG, job) == job
    assert route.call_count == 0


async def test_empty_last_page_not_complete(client, mock, monkeypatch):
    monkeypatch.setattr(amazon, "PAGE", 25)
    india = load_json("amazon", "india_page1")
    india["hits"] = 60
    empty = {**india, "jobs": []}

    def respond(request):
        if "base_query" in request.url.params:
            return httpx.Response(200, json={**india, "hits": len(india["jobs"])})
        last = request.url.params["offset"] == "50"  # the final page comes back empty
        return httpx.Response(200, json=empty if last else india)

    mock.get(SEARCH).mock(side_effect=respond)
    assert (await AmazonAdapter().list_jobs(client, CFG, "full")).complete is False
