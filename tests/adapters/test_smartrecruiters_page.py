from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.smartrecruiters_page import SR_ID, apply_posting, fetch_posting
from tests.conftest import load_fixture, load_json

URL = "https://jobs.smartrecruiters.com/PHONEPELIMITED/1000000000002543-intern-company-secretary"
MISSING = "https://jobs.smartrecruiters.com/PHONEPELIMITED/1000000000000000-missing"


async def test_sr_posting_fills_description(client, mock):
    mock.get(URL).mock(
        return_value=httpx.Response(200, json=load_json("smartrecruiters", "posting"))
    )
    posting = await fetch_posting(client, URL)
    job = apply_posting(RawJob(external_id="1000000000002543", title="x", url=URL), posting)
    html = job.description_html
    heads = [s["title"] for s in posting["content"]["sections"].values() if s.get("text")]
    assert [html.index(f"<h3>{h}</h3>") for h in heads] == sorted(
        html.index(f"<h3>{h}</h3>") for h in heads
    )
    assert len(heads) >= 3
    assert job.posted_at == datetime(2026, 9, 18, 7, 7, 50, 839000, tzinfo=UTC)
    assert job.employment_type == "Intern"
    assert job.apply_url == posting["applyUrl"]
    assert job.locations == [posting["jobAdLocation"]]


async def test_sr_keeps_listing_locations(client, mock):
    posting = load_json("smartrecruiters", "posting")
    job = RawJob(external_id="1", title="x", url=URL, locations=["Bengaluru"])
    assert apply_posting(job, posting).locations == ["Bengaluru"]


async def test_sr_missing_is_gone(client, mock):
    body = load_fixture("smartrecruiters", "missing")
    mock.get(MISSING).mock(
        return_value=httpx.Response(404, content=body, headers={"content-type": "text/html"})
    )
    assert await fetch_posting(client, MISSING) is GONE


async def test_sr_html_answer_raises_parse_error(client, mock):
    body = load_fixture("smartrecruiters", "missing")
    mock.get(URL).mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "text/html"})
    )
    with pytest.raises(ParseError):
        await fetch_posting(client, URL)


async def test_sr_sends_json_accept(client, mock):
    route = mock.get(URL).mock(
        return_value=httpx.Response(200, json=load_json("smartrecruiters", "posting"))
    )
    await fetch_posting(client, URL)
    assert route.calls.last.request.headers["accept"] == "application/json"


def test_sr_id_from_url():
    assert SR_ID.search(URL).group(1) == "1000000000002543"
