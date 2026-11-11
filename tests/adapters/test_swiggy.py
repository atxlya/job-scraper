import httpx
import pytest

from app.adapters.base import ParseError
from app.adapters.company.swiggy import URL, SwiggyAdapter
from app.adapters.text import from_ms
from tests.conftest import load_json


async def test_parses_listing(client, mock):
    body = load_json("swiggy", "jobs")
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    res = await SwiggyAdapter().list_jobs(client, {}, "full")
    assert len(res.jobs) == len(body["jobs"])  # the fixture is trimmed to 25 of `total`
    assert res.reported_total == body["total"]
    j, r = res.jobs[0], body["jobs"][0]
    assert j.external_id.isdigit() and j.external_id in r["u"]
    assert j.title == r["t"] and j.url == r["u"] and j.locations == [r["l"]]
    assert j.posted_at == from_ms(r["d"])
    assert j.country_codes == ["IN"]


async def test_remote_and_hybrid_flags(client, mock):
    body = load_json("swiggy", "jobs")
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    res = await SwiggyAdapter().list_jobs(client, {}, "full")
    by_id = {j.url: j for j in res.jobs}
    for r in body["jobs"]:
        want = "remote" if r["r"] == 1 else "hybrid" if r["h"] == 1 else None
        assert by_id[r["u"]].remote_type == want
    assert any(j.remote_type == "hybrid" for j in res.jobs)


async def test_missing_jobs_key_raises_parse_error(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, json={"total": 1}))
    with pytest.raises(ParseError):
        await SwiggyAdapter().list_jobs(client, {}, "full")


async def test_row_without_link_is_skipped(client, mock):
    body = load_json("swiggy", "jobs")
    body["jobs"][0]["u"] = "https://example-ats.com/job/1"
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    res = await SwiggyAdapter().list_jobs(client, {}, "full")
    assert len(res.jobs) == len(body["jobs"]) - 1


async def test_no_usable_rows_raises_parse_error(client, mock):
    body = load_json("swiggy", "jobs")
    for r in body["jobs"]:
        r["u"] = ""
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(ParseError):
        await SwiggyAdapter().list_jobs(client, {}, "full")
