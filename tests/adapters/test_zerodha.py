import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.company.zerodha import URL, ZerodhaAdapter
from app.sources.checks import evaluate
from tests.conftest import load_json

CFG = {"allow_empty": True}


async def test_empty_answer_is_healthy(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, json=load_json("zerodha", "empty")))
    res = await ZerodhaAdapter().list_jobs(client, CFG, "full")
    assert res.jobs == [] and res.complete is True and res.reported_total == 0
    assert evaluate(res, "full", CFG) == []


async def test_unsuccessful_raises_parse_error(client, mock):
    body = load_json("zerodha", "empty")
    body["success"] = False
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(ParseError):
        await ZerodhaAdapter().list_jobs(client, CFG, "full")


async def test_detail_gone_when_not_listed(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, json=load_json("zerodha", "empty")))
    job = RawJob(external_id="backend-dev", title="Backend dev", url=URL)
    assert await ZerodhaAdapter().fetch_detail(client, CFG, job) is GONE


async def test_non_object_row_raises_parse_error(client, mock):
    body = load_json("zerodha", "empty")
    body["data"] = ["not a job"]
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(ParseError):
        await ZerodhaAdapter().list_jobs(client, CFG, "full")


async def test_detail_reads_the_list_once_per_run(client, mock):
    route = mock.get(URL).mock(return_value=httpx.Response(200, json=load_json("zerodha", "empty")))
    adapter = ZerodhaAdapter()
    for key in ("a", "b", "c"):
        job = RawJob(external_id=key, title=key, url=URL)
        assert await adapter.fetch_detail(client, CFG, job) is GONE
    assert route.call_count == 1
