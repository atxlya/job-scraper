from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.company.tataelxsi import TataElxsiAdapter
from tests.conftest import load_fixture

BASE = "https://www.tataelxsi.com/careers/job-openings"
ROBOTS = """User-agent: *
Disallow: /admin/
Disallow: /login/
Disallow: /search?
Disallow: /storage/
Disallow: /tmp/
Disallow: /cgi-bin/
Disallow: /*?utm_*
Disallow: /FrontEnd/
Disallow: /cdn-cgi/
"""


@pytest.fixture(autouse=True)
def te_robots(mock):
    mock.get("https://www.tataelxsi.com/robots.txt").mock(
        return_value=httpx.Response(200, text=ROBOTS)
    )


def html(name):
    return httpx.Response(200, content=load_fixture("tataelxsi", name))


async def test_parses_cards(client, mock):
    mock.get(BASE, params={"page": "1"}).mock(return_value=html("page_1"))
    res = await TataElxsiAdapter().list_jobs(client, {}, "incremental")
    assert len(res.jobs) == 8
    first = res.jobs[0]
    assert first.external_id == "java-developer"
    assert first.title == "JAVA Developer"
    assert first.url == f"{BASE}/java-developer"
    assert first.locations == ["Bangalore", "Chennai", "Hyderabad"]
    assert first.country_codes == ["IN"]
    assert first.posted_at == datetime(2026, 11, 5, tzinfo=UTC)
    assert res.reported_total is None


async def test_full_reads_every_page(client, mock):
    route = mock.get(BASE).mock(
        side_effect=lambda req: html("page_11" if req.url.params["page"] == "11" else "page_1")
    )
    res = await TataElxsiAdapter().list_jobs(client, {}, "full")
    assert [c.request.url.params["page"] for c in route.calls] == [str(n) for n in range(1, 12)]
    assert res.complete is True
    assert len({j.external_id for j in res.jobs}) >= 8
    # page 11 has cards with an empty date: listed without posted_at, not a parse error
    assert any(j.posted_at is None for j in res.jobs)


async def test_incremental_reads_page_one(client, mock):
    route = mock.get(BASE, params={"page": "1"}).mock(return_value=html("page_1"))
    res = await TataElxsiAdapter().list_jobs(client, {}, "incremental")
    assert route.call_count == 1
    assert res.complete is False


async def test_detail_page(client, mock):
    mock.get(f"{BASE}/java-developer").mock(return_value=html("job"))
    listed = RawJob(
        external_id="java-developer", title="JAVA Developer", url=f"{BASE}/java-developer"
    )
    job = await TataElxsiAdapter().fetch_detail(client, {}, listed)
    assert job.external_id == "java-developer"
    assert job.title == "JAVA Developer"
    assert "Key Skills Required" in job.description_html
    assert job.apply_url.startswith("https://oneelxsi.ramcoes.com/")


async def test_missing_redirect_is_gone(client, mock):
    url = f"{BASE}/no-such-job-xyz"
    mock.get(url).mock(
        return_value=httpx.Response(302, headers={"Location": "https://www.tataelxsi.com"})
    )
    home = mock.get("https://www.tataelxsi.com").mock(return_value=html("home"))
    listed = RawJob(external_id="no-such-job-xyz", title="x", url=url)
    assert await TataElxsiAdapter().fetch_detail(client, {}, listed) is GONE
    assert not home.called


async def test_other_redirect_is_followed(client, mock):
    old = f"{BASE}/old-slug"
    mock.get(old).mock(
        return_value=httpx.Response(302, headers={"Location": f"{BASE}/java-developer"})
    )
    mock.get(f"{BASE}/java-developer").mock(return_value=html("job"))
    listed = RawJob(external_id="old-slug", title="x", url=old)
    job = await TataElxsiAdapter().fetch_detail(client, {}, listed)
    assert job.title == "JAVA Developer"


async def test_home_page_raises_parse_error(client, mock):
    mock.get(BASE, params={"page": "1"}).mock(return_value=html("home"))
    with pytest.raises(ParseError):
        await TataElxsiAdapter().list_jobs(client, {}, "incremental")
