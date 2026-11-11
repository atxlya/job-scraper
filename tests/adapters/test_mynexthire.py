import json
from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.mynexthire import MyNextHireAdapter
from tests.conftest import FIXTURES, load_fixture

CFG = {"host": "sharechat.mynexthire.com"}
LIST = "https://sharechat.mynexthire.com/employer/careers/reqlist/get"
REQ = "https://sharechat.mynexthire.com/employer/careers/req/get"
DROPPED = ("coordinatorName", "coordinatorEmployeeMobile", "hiringManagerName")


def answer(name: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=load_fixture("mynexthire", name))


async def test_parses_list(client, mock):
    route = mock.post(LIST).mock(return_value=answer("reqlist"))
    res = await MyNextHireAdapter().list_jobs(client, CFG, "full")
    assert json.loads(route.calls[0].request.content) == {
        "source": "careers",
        "code": "",
        "filterByBuId": -1,
    }
    assert len(res.jobs) == 11 and res.reported_total is None and res.complete is True
    jobs = {j.external_id: j for j in res.jobs}
    intern = jobs["2491"]
    assert intern.title == "Marketing Intern"
    assert intern.platform_flags == {"intern": True}
    assert intern.employment_type == "intern"
    assert intern.posted_at == datetime(2026, 10, 30, 9, 31, 6, 398000, tzinfo=UTC)
    assert intern.locations == ["Bangalore"] and intern.country_codes == ["IN"]
    assert intern.url == "https://sharechat.mynexthire.com/employer/jobs"
    writer = jobs["2496"]
    assert writer.platform_flags == {}
    assert "ShareChat" in writer.description_html
    assert writer.country_codes == ["IN"]


def job() -> RawJob:
    return RawJob(external_id="2491", title="Marketing Intern", url="https://x")


async def test_detail_parses(client, mock):
    route = mock.post(REQ).mock(return_value=answer("req_2491"))
    got = await MyNextHireAdapter().fetch_detail(client, CFG, job())
    assert got.title == "Marketing Intern" and got.platform_flags == {"intern": True}
    assert json.loads(route.calls[0].request.content)["reqId"] == 2491


async def test_detail_gone_on_417(client, mock):
    mock.post(REQ).mock(return_value=answer("req_missing", 417))
    assert await MyNextHireAdapter().fetch_detail(client, CFG, job()) is GONE


async def test_detail_500_raises(client, mock):
    mock.post(REQ).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await MyNextHireAdapter().fetch_detail(client, CFG, job())


def test_fixtures_hold_no_contact_fields():
    for path in (FIXTURES / "mynexthire").iterdir():
        text = path.read_text(encoding="utf-8")
        assert not any(key in text for key in DROPPED), path.name


async def test_list_without_key_raises_parse_error(client, mock):
    mock.post(LIST).mock(return_value=httpx.Response(200, json={"requesterTitle": ""}))
    with pytest.raises(ParseError):
        await MyNextHireAdapter().list_jobs(client, CFG, "full")


async def test_detail_417_with_another_message_raises(client, mock):
    mock.post(REQ).mock(
        return_value=httpx.Response(417, json={"errorMessage": "Session expired, try again."})
    )
    with pytest.raises(ParseError, match="417"):
        await MyNextHireAdapter().fetch_detail(
            client, CFG, RawJob(external_id="1", title="t", url="u")
        )
