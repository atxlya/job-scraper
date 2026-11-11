import httpx
import pytest

from app.adapters.base import ParseError
from app.adapters.company.phonepe import URL, PhonePeAdapter
from app.adapters.smartrecruiters_page import SR_ID
from tests.conftest import load_json


def serve(mock, body):
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))


def public(body):
    return [
        r
        for r in body["results"]
        if r.get("status") == "PUBLIC" and SR_ID.search(r.get("applyUrl") or "")
    ]


async def test_keeps_only_public_with_id(client, mock):
    body = load_json("phonepe", "latest")
    serve(mock, body)
    res = await PhonePeAdapter().list_jobs(client, {}, "incremental")
    rows = public(body)
    assert len(res.jobs) == len(rows) > 0
    j, r = res.jobs[0], rows[0]
    assert j.external_id == SR_ID.search(r["applyUrl"]).group(1)
    assert j.url == r["applyUrl"] and j.title == r["title"]
    assert j.locations == [r["location"]] and j.employment_type == r["type"]


async def test_intern_type_sets_flag(client, mock):
    serve(mock, load_json("phonepe", "latest"))
    res = await PhonePeAdapter().list_jobs(client, {}, "full")
    flagged = [j.title for j in res.jobs if j.platform_flags.get("intern")]
    assert flagged == ["Intern, Company Secretary"]


async def test_complete_only_when_results_match_total(client, mock):
    body = load_json("phonepe", "latest")
    body["totalCount"] = len(body["results"])
    serve(mock, body)
    assert (await PhonePeAdapter().list_jobs(client, {}, "full")).complete is True
    body["results"] = body["results"][:-1]
    mock.routes.clear()
    serve(mock, body)
    assert (await PhonePeAdapter().list_jobs(client, {}, "full")).complete is False


async def test_missing_results_raises_parse_error(client, mock):
    serve(mock, {"totalCount": 3})
    with pytest.raises(ParseError):
        await PhonePeAdapter().list_jobs(client, {}, "full")
