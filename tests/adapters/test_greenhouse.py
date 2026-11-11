import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.greenhouse import GreenhouseAdapter
from tests.conftest import load_json

API = "https://boards-api.greenhouse.io/v1/boards"
CFG = {"board": "groww"}


def serve(mock, name, url=f"{API}/groww/jobs", status=200):
    body = load_json("greenhouse", name)
    return mock.get(url).mock(return_value=httpx.Response(status, json=body)), body


async def test_parses_listing(client, mock):
    _, body = serve(mock, "groww_full")
    res = await GreenhouseAdapter().list_jobs(client, CFG, "full")
    assert len(res.jobs) == body["meta"]["total"] == 9
    assert res.reported_total == 9
    j, p = res.jobs[0], body["jobs"][0]
    assert j.external_id == str(p["id"]) and j.title == p["title"]
    assert j.url == p["absolute_url"]
    assert j.locations[0] == p["location"]["name"]
    assert j.country_codes == ["IN"]
    assert j.posted_at is not None and j.posted_at.isoformat().startswith(p["first_published"][:10])


async def test_content_is_unescaped(client, mock):
    serve(mock, "groww_full")
    res = await GreenhouseAdapter().list_jobs(client, CFG, "full")
    for j in res.jobs:
        assert j.description_html.startswith("<")
        assert "&lt;" not in j.description_html


async def test_incremental_omits_content(client, mock):
    route, _ = serve(mock, "groww_light")
    res = await GreenhouseAdapter().list_jobs(client, CFG, "incremental")
    assert "content" not in route.calls.last.request.url.params
    assert res.jobs and all(j.description_html is None for j in res.jobs)
    assert res.complete is False


async def test_full_requests_content(client, mock):
    route, _ = serve(mock, "groww_full")
    res = await GreenhouseAdapter().list_jobs(client, CFG, "full")
    assert route.calls.last.request.url.params["content"] == "true"
    assert res.complete is True


async def test_employment_type_from_metadata(client, mock):
    serve(mock, "inmobi", url=f"{API}/inmobi/jobs")
    res = await GreenhouseAdapter().list_jobs(client, {"board": "inmobi"}, "full")
    assert res.jobs[0].employment_type == "Direct Consultant"


async def test_detail_fills_description(client, mock):
    body = load_json("greenhouse", "groww_detail")
    mock.get(f"{API}/groww/jobs/{body['id']}").mock(return_value=httpx.Response(200, json=body))
    job = RawJob(external_id=str(body["id"]), title="x", url=body["absolute_url"])
    got = await GreenhouseAdapter().fetch_detail(client, CFG, job)
    assert got.description_html.startswith("<") and "&lt;" not in got.description_html


async def test_detail_missing_is_gone(client, mock):
    serve(mock, "missing", url=f"{API}/groww/jobs/1", status=404)
    job = RawJob(external_id="1", title="x", url="https://job-boards.greenhouse.io/groww/jobs/1")
    assert await GreenhouseAdapter().fetch_detail(client, CFG, job) is GONE


async def test_missing_jobs_key_raises_parse_error(client, mock):
    mock.get(f"{API}/groww/jobs").mock(return_value=httpx.Response(200, json={"meta": {}}))
    with pytest.raises(ParseError):
        await GreenhouseAdapter().list_jobs(client, CFG, "full")
