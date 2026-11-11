import json
from datetime import UTC, datetime

import httpx

from app.adapters.base import RawJob
from app.adapters.company import ibm
from app.adapters.company.ibm import SEARCH, IbmAdapter
from tests.conftest import load_json


def serve(mock, body):
    return mock.post(SEARCH).mock(return_value=httpx.Response(200, json=body))


async def test_parses_listing(client, mock):
    body = load_json("ibm", "page1")
    route = serve(mock, body)
    res = await IbmAdapter().list_jobs(client, {}, "incremental")
    src = body["hits"]["hits"][0]["_source"]
    j = res.jobs[0]
    assert j.external_id == src["url"].split("jobId=")[1]
    assert j.title == src["title"] and j.url == src["url"]
    assert j.locations == [src["field_keyword_19"]]
    assert j.posted_at == datetime.fromisoformat(src["dcdate"]).replace(tzinfo=UTC)
    assert j.platform_flags == {"intern": True}
    assert j.description_html.startswith("<p>")
    assert res.reported_total == body["hits"]["total"]["value"]
    sent = json.loads(route.calls.last.request.content)
    assert sent["post_filter"]["bool"]["must"] == [{"term": {"field_keyword_18": "Internship"}}]
    assert sent["sort"] == [{"dcdate": "desc"}] and sent["from"] == 0


async def test_country_from_suffix(client, mock):
    serve(mock, load_json("ibm", "page1"))
    res = await IbmAdapter().list_jobs(client, {}, "incremental")
    by_loc = {j.locations[0]: j.country_codes for j in res.jobs}
    assert by_loc["Singapore, SG"] == ["SG"]
    assert by_loc["COLUMBIA, US"] == ["US"]
    hybrid = [j for j in res.jobs if j.remote_type == "hybrid"]
    assert hybrid and all(j.remote_type in (None, "hybrid") for j in res.jobs)


async def test_full_pages_until_total(client, mock, monkeypatch):
    monkeypatch.setattr(ibm, "SIZE", 25)
    body = load_json("ibm", "page1")
    body["hits"]["total"]["value"] = 60
    route = serve(mock, body)
    res = await IbmAdapter().list_jobs(client, {}, "full")
    assert [json.loads(c.request.content)["from"] for c in route.calls] == [0, 25, 50]
    assert res.complete is True


async def test_ibm_never_requests_careers_site(client, mock):
    serve(mock, load_json("ibm", "page1"))
    careers = mock.route(host="careers.ibm.com").mock(return_value=httpx.Response(200))
    res = await IbmAdapter().list_jobs(client, {}, "full")
    job = res.jobs[0]
    assert await IbmAdapter().fetch_detail(client, {}, job) == job
    blank = RawJob(
        external_id="1", title="x", url="https://careers.ibm.com/careers/JobDetail?jobId=1"
    )
    assert await IbmAdapter().fetch_detail(client, {}, blank) == blank
    assert careers.call_count == 0


async def test_empty_last_page_not_complete(client, mock, monkeypatch):
    monkeypatch.setattr(ibm, "SIZE", 25)
    body = load_json("ibm", "page1")
    body["hits"]["total"]["value"] = 60
    empty = {"hits": {"total": {"value": 60}, "hits": []}}

    def respond(request):
        start = json.loads(request.content)["from"]
        return httpx.Response(200, json=empty if start == 50 else body)  # final page empty

    mock.post(SEARCH).mock(side_effect=respond)
    assert (await IbmAdapter().list_jobs(client, {}, "full")).complete is False
