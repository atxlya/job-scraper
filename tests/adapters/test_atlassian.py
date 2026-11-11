import httpx
import pytest

from app.adapters.base import ParseError, RawJob
from app.adapters.company.atlassian import URL, AtlassianAdapter
from tests.conftest import load_json


async def test_parses_listing(client, mock):
    body = load_json("atlassian", "listings")
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    res = await AtlassianAdapter().list_jobs(client, {}, "full")
    assert len(res.jobs) == len(body) and res.complete is True
    j, p = res.jobs[0], body[0]
    assert j.external_id == str(p["id"]) and j.title == p["title"]
    assert j.url == p["portalJobPost"]["portalUrl"] and j.apply_url == p["applyUrl"]
    assert j.locations == p["locations"]
    assert j.description_html.startswith(p["overview"][:40])
    assert "<h3>Responsibilities</h3>" in j.description_html
    assert j.posted_at is None and res.reported_total is None


async def test_remote_only_locations(client, mock):
    body = load_json("atlassian", "listings")
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    res = await AtlassianAdapter().list_jobs(client, {}, "full")
    for j in res.jobs:
        all_remote = all(loc.startswith("Remote") for loc in j.locations)
        assert (j.remote_type == "remote") == all_remote
    assert any(j.remote_type == "remote" for j in res.jobs)


async def test_not_a_list_raises_parse_error(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, json={"error": "down"}))
    with pytest.raises(ParseError):
        await AtlassianAdapter().list_jobs(client, {}, "full")


async def test_detail_makes_no_request(client, mock):
    job = RawJob(external_id="1", title="x", url="https://x/1")
    assert await AtlassianAdapter().fetch_detail(client, {}, job) == job
