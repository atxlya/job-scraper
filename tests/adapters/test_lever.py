import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.lever import LeverAdapter
from app.adapters.text import from_ms
from tests.conftest import load_json

LIST = "https://api.lever.co/v0/postings/paytm"
CFG = {"site": "paytm"}


def serve(mock, name, url=LIST, status=200):
    body = load_json("lever", name)
    return mock.get(url).mock(return_value=httpx.Response(status, json=body)), body


async def test_parses_listing(client, mock):
    _, body = serve(mock, "paytm_interns")
    res = await LeverAdapter().list_jobs(client, CFG, "incremental")
    assert len(res.jobs) == len(body)
    j, p = res.jobs[0], body[0]
    assert j.external_id == p["id"]
    assert j.title == p["text"]
    assert j.url == p["hostedUrl"] and j.apply_url == p["applyUrl"]
    assert j.posted_at == from_ms(p["createdAt"])
    assert p["country"] in j.country_codes
    assert j.employment_type == p["categories"]["commitment"]
    assert res.reported_total is None


async def test_intern_commitment_sets_flag(client, mock):
    serve(mock, "paytm_interns")
    res = await LeverAdapter().list_jobs(client, CFG, "full")
    assert res.jobs and all(j.platform_flags == {"intern": True} for j in res.jobs)
    mock.routes.clear()
    serve(mock, "cred", url="https://api.lever.co/v0/postings/cred")
    res = await LeverAdapter().list_jobs(client, {"site": "cred"}, "full")
    assert res.jobs and not any(j.platform_flags for j in res.jobs)


async def test_lists_and_additional_in_description(client, mock):
    _, body = serve(mock, "cred", url="https://api.lever.co/v0/postings/cred")
    res = await LeverAdapter().list_jobs(client, {"site": "cred"}, "full")
    p = next(p for p in body if any(li["text"] for li in p["lists"]))
    li = next(li for li in p["lists"] if li["text"])
    j = next(j for j in res.jobs if j.external_id == p["id"])
    assert f"<h3>{li['text']}</h3><ul>{li['content']}</ul>" in j.description_html
    assert j.remote_type == p["workplaceType"]


async def test_complete_only_in_full(client, mock):
    serve(mock, "paytm_interns")
    assert (await LeverAdapter().list_jobs(client, CFG, "incremental")).complete is False
    assert (await LeverAdapter().list_jobs(client, CFG, "full")).complete is True


async def test_detail_fills_job(client, mock):
    body = load_json("lever", "paytm_detail")
    mock.get(f"{LIST}/{body['id']}").mock(return_value=httpx.Response(200, json=body))
    job = RawJob(external_id=body["id"], title="x", url=body["hostedUrl"])
    got = await LeverAdapter().fetch_detail(client, CFG, job)
    assert got.title == body["text"] and got.description_html


async def test_detail_missing_is_gone(client, mock):
    serve(mock, "missing", url=f"{LIST}/gone", status=404)
    job = RawJob(external_id="gone", title="x", url="https://jobs.lever.co/paytm/gone")
    assert await LeverAdapter().fetch_detail(client, CFG, job) is GONE


async def test_not_a_list_raises_parse_error(client, mock):
    mock.get(LIST).mock(return_value=httpx.Response(200, json={"ok": False}))
    with pytest.raises(ParseError):
        await LeverAdapter().list_jobs(client, CFG, "full")


@pytest.mark.parametrize(
    ("commitment", "flagged"),
    [
        ("Intern", True),
        ("Internship", True),
        ("Summer Interns", True),
        ("International Assignment", False),
        ("Internal Transfer", False),
    ],
)
async def test_intern_commitment_words(client, mock, commitment, flagged):
    body = load_json("lever", "paytm_interns")[:1]
    body[0]["categories"]["commitment"] = commitment
    mock.get(LIST).mock(return_value=httpx.Response(200, json=body))
    res = await LeverAdapter().list_jobs(client, CFG, "full")
    assert bool(res.jobs[0].platform_flags.get("intern")) is flagged


async def test_list_without_content_leaves_no_empty_heading(client, mock):
    body = load_json("lever", "cred")
    p = next(p for p in body if any(li["text"] for li in p["lists"]))
    li = next(li for li in p["lists"] if li["text"])
    li["content"] = "  "
    mock.get("https://api.lever.co/v0/postings/cred").mock(
        return_value=httpx.Response(200, json=body)
    )
    res = await LeverAdapter().list_jobs(client, {"site": "cred"}, "full")
    j = next(j for j in res.jobs if j.external_id == p["id"])
    assert f"<h3>{li['text']}</h3>" not in j.description_html
    assert "<ul>  </ul>" not in j.description_html
