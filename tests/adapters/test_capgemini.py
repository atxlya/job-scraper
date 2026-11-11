import httpx
import pytest

from app.adapters.base import ParseError
from app.adapters.company import capgemini
from app.adapters.company.capgemini import URL, CapgeminiAdapter
from tests.conftest import load_json

CFG = {"country_code": "en-in"}


async def test_parses_listing(client, mock):
    body = load_json("capgemini", "p1")
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    res = await CapgeminiAdapter().list_jobs(client, CFG, "incremental")
    p, j = body["data"][0], res.jobs[0]
    assert j.external_id == p["id"] and j.title == p["title"]
    assert j.url == p["apply_job_url"]
    assert j.locations == [s.strip() for s in p["location"].split(",")]
    assert "IN" in j.country_codes
    assert j.employment_type == p["contract_type"] and j.description_html == p["description"]
    assert res.reported_total == body["total"]
    assert not any(j.platform_flags for j in res.jobs)  # no student rows in India today


async def test_full_pages_until_total(client, mock, monkeypatch):
    monkeypatch.setattr(capgemini, "PAGE", 25)
    p1, p2 = load_json("capgemini", "p1"), load_json("capgemini", "p2")
    p1["total"] = p2["total"] = 60

    def respond(request):
        return httpx.Response(200, json=p1 if request.url.params["page"] == "1" else p2)

    route = mock.get(URL).mock(side_effect=respond)
    res = await CapgeminiAdapter().list_jobs(client, CFG, "full")
    assert [int(c.request.url.params["page"]) for c in route.calls] == [1, 2, 3]
    assert res.complete is True


async def test_missing_data_raises_parse_error(client, mock):
    mock.get(URL).mock(return_value=httpx.Response(200, json={"total": 3}))
    with pytest.raises(ParseError):
        await CapgeminiAdapter().list_jobs(client, CFG, "full")


@pytest.mark.parametrize(
    ("contract", "flagged"),
    [("Internship", True), ("Student", True), ("International", False), ("Internal", False)],
)
async def test_intern_contract_words(client, mock, contract, flagged):
    body = load_json("capgemini", "p1")
    body["data"] = body["data"][:1]
    body["data"][0]["contract_type"] = contract
    body["total"] = 1
    mock.get(URL).mock(return_value=httpx.Response(200, json=body))
    res = await CapgeminiAdapter().list_jobs(client, CFG, "full")
    assert bool(res.jobs[0].platform_flags.get("intern")) is flagged


async def test_empty_last_page_not_complete(client, mock, monkeypatch):
    monkeypatch.setattr(capgemini, "PAGE", 25)
    p1 = load_json("capgemini", "p1")
    p1["total"] = 60
    empty = {**p1, "data": []}

    def respond(request):
        last = request.url.params["page"] == "3"  # the final page comes back empty
        return httpx.Response(200, json=empty if last else p1)

    mock.get(URL).mock(side_effect=respond)
    assert (await CapgeminiAdapter().list_jobs(client, CFG, "full")).complete is False


async def test_incremental_reads_every_page(client, mock, monkeypatch):
    # Pages aren't newest-first, so the 30-minute run must read them all too.
    monkeypatch.setattr(capgemini, "PAGE", 25)
    p1, p2 = load_json("capgemini", "p1"), load_json("capgemini", "p2")
    p1["total"] = p2["total"] = 60
    route = mock.get(URL).mock(
        side_effect=lambda r: httpx.Response(200, json=p1 if r.url.params["page"] == "1" else p2)
    )
    res = await CapgeminiAdapter().list_jobs(client, CFG, "incremental")
    assert [int(c.request.url.params["page"]) for c in route.calls] == [1, 2, 3]
    assert res.complete is False
