import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.spire2grow import API, Spire2GrowAdapter
from app.adapters.text import from_ms
from tests.conftest import load_fixture, load_json

CFG = {"domain": "jobs.myntra.com"}
SEARCH = f"{API}/requisition/_search"


@pytest.fixture
def workspace(mock):
    return mock.get(f"{API}/workspaceId", params={"domain": "jobs.myntra.com"}).mock(
        return_value=httpx.Response(200, content=load_fixture("spire2grow", "workspace"))
    )


def search(data=None):
    return httpx.Response(200, json=data if data is not None else load_json("spire2grow", "search"))


async def test_parses_search(client, mock, workspace):
    mock.get(SEARCH).mock(return_value=search())
    res = await Spire2GrowAdapter().list_jobs(client, CFG, "full")
    assert res.reported_total == 51 and len(res.jobs) == 51 and res.complete is True
    job = next(j for j in res.jobs if j.external_id == "7093610092")
    assert job.title == "Technical Lead Backend - Artificial Intelligence"
    assert job.locations == ["Bangalore, Karnataka, India"]
    assert job.country_codes == ["IN"]
    assert job.remote_type == "hybrid"
    assert job.employment_type == "full_time"
    assert job.posted_at == from_ms(1794378650000)
    assert job.url == "https://jobs.myntra.com/jobs/7093610092"
    assert "AI-native platform" in job.description_html
    assert job.platform_flags == {}


async def test_sends_workspace_header(client, mock, workspace):
    route = mock.get(SEARCH).mock(return_value=search())
    await Spire2GrowAdapter().list_jobs(client, CFG, "incremental")
    sent = route.calls[0].request
    assert sent.headers["WorkspaceId"] == "MYNTRA-93as3"
    assert sent.headers["language"] == "en"
    assert sent.url.params["page"] == "1" and sent.url.params["size"] == "100"


async def test_apprenticeship_and_internship_flagged(client, mock, workspace):
    data = load_json("spire2grow", "search")
    data["entities"][0]["employmentType"] = "INTERNSHIP"
    mock.get(SEARCH).mock(return_value=search(data))
    jobs = {
        j.external_id: j for j in (await Spire2GrowAdapter().list_jobs(client, CFG, "full")).jobs
    }
    assert jobs[data["entities"][0]["displayId"]].platform_flags == {"intern": True}
    assert jobs["2455903149"].platform_flags == {"intern": True}  # real "APPRENTICESHIP"


def job() -> RawJob:
    return RawJob(
        external_id="7093610092", title="t", url="https://jobs.myntra.com/jobs/7093610092"
    )


async def test_detail_parses(client, mock, workspace):
    mock.get(f"{API}/requisition/displayId/7093610092").mock(
        return_value=httpx.Response(200, content=load_fixture("spire2grow", "detail"))
    )
    got = await Spire2GrowAdapter().fetch_detail(client, CFG, job())
    assert got.title == "Technical Lead Backend - Artificial Intelligence"
    assert "AI-native platform" in got.description_html


async def test_detail_gone_on_404(client, mock, workspace):
    mock.get(f"{API}/requisition/displayId/7093610092").mock(
        return_value=httpx.Response(404, content=load_fixture("spire2grow", "missing"))
    )
    assert await Spire2GrowAdapter().fetch_detail(client, CFG, job()) is GONE


async def test_empty_workspace_raises_parse_error(client, mock):
    mock.get(f"{API}/workspaceId").mock(return_value=httpx.Response(200, text=""))
    with pytest.raises(ParseError):
        await Spire2GrowAdapter().list_jobs(client, CFG, "full")


async def test_search_without_entities_raises(client, mock, workspace):
    mock.get(SEARCH).mock(return_value=httpx.Response(200, json={"total": 3}))
    with pytest.raises(ParseError):
        await Spire2GrowAdapter().list_jobs(client, CFG, "full")


async def test_workspace_asked_once_per_run(client, mock, workspace):
    for n in ("7093610092", "7093610093"):
        mock.get(f"{API}/requisition/displayId/{n}").mock(
            return_value=httpx.Response(200, content=load_fixture("spire2grow", "detail"))
        )
    adapter = Spire2GrowAdapter()
    for n in ("7093610092", "7093610093"):
        await adapter.fetch_detail(client, CFG, job().model_copy(update={"external_id": n}))
    assert workspace.call_count == 1
