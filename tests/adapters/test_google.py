import httpx
import pytest
import respx

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.company.google import GoogleAdapter
from app.http.client import PoliteClient
from tests.conftest import load_fixture

RESULTS = "https://www.google.com/about/careers/applications/jobs/results/"
CFG = {
    "queries": [
        {"target_level": "INTERN_AND_APPRENTICE", "location": "India"},
        {"target_level": "INTERN_AND_APPRENTICE", "location": "United States"},
    ]
}
ROBOTS = (
    "User-agent: *\n"
    "Disallow: /about/careers/applications/jobs/results?page=\n"
    "Disallow: /about/careers/applications/jobs/results/?page=\n"
    "Disallow: /about/careers/applications/jobs/results?*&page=\n"
    "Disallow: /about/careers/applications/jobs/results/?*&page=\n"
)


@pytest.fixture
def client():
    async def nosleep(_s):
        return None

    return PoliteClient(min_interval_s=0, sleep=nosleep)


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        m.get("https://www.google.com/robots.txt").mock(
            return_value=httpx.Response(200, text=ROBOTS)
        )
        yield m


def html(name: str) -> httpx.Response:
    return httpx.Response(
        200, content=load_fixture("google", name), headers={"content-type": "text/html"}
    )


def by_location(request):
    loc = request.url.params.get("location")
    return html("intern_india" if loc == "India" else "intern_us")


async def test_google_parses_ds1(client, mock):
    mock.get(RESULTS).mock(side_effect=by_location)
    res = await GoogleAdapter().list_jobs(client, CFG, "full")
    assert len(res.jobs) == 3 + 18  # the recorded pages' real job counts
    j = next(j for j in res.jobs if j.external_id == "125423735539671750")
    assert j.title == "Student Researcher, 2027"
    assert j.url == RESULTS + "125423735539671750-student-researcher-2027"
    assert j.apply_url and "signin?jobId=" in j.apply_url
    assert j.country_codes == ["IN"]
    assert j.posted_at is not None and j.posted_at.year == 2026
    assert "Minimum qualifications" in (j.description_html or "")
    assert j.platform_flags == {"intern": True}


async def test_google_never_requests_page_param(client, mock):
    route = mock.get(RESULTS).mock(side_effect=by_location)
    for mode in ("incremental", "full"):
        await GoogleAdapter().list_jobs(client, CFG, mode)
    assert route.call_count == 4
    assert all("page=" not in str(c.request.url) for c in route.calls)
    assert all(c.request.url.params["sort_by"] == "date" for c in route.calls)


async def test_google_complete_only_when_every_query_fits_page1(client, mock):
    mock.get(RESULTS).mock(side_effect=by_location)
    full = await GoogleAdapter().list_jobs(client, CFG, "full")
    assert full.complete is True  # India total 3, US total 18: both fit on page 1
    assert full.reported_total == 21
    inc = await GoogleAdapter().list_jobs(client, CFG, "incremental")
    assert inc.complete is False


async def test_parse_error_marks_failed(client, mock):
    mock.get(RESULTS).mock(
        return_value=httpx.Response(
            200, text="<html>no data</html>", headers={"content-type": "text/html"}
        )
    )
    with pytest.raises(ParseError):
        await GoogleAdapter().list_jobs(client, CFG, "full")


async def test_google_detail_present(client, mock):
    url = RESULTS + "125423735539671750-student-researcher-2027"
    mock.get(url).mock(return_value=html("detail"))
    job = RawJob(external_id="125423735539671750", title="Student Researcher, 2027", url=url)
    out = await GoogleAdapter().fetch_detail(client, {}, job)
    assert out is not GONE and out.description_html


async def test_google_gone_on_empty_ds0(client, mock):
    url = RESULTS + "1-does-not-exist"
    mock.get(url).mock(return_value=html("detail_missing"))
    job = RawJob(external_id="1", title="x", url=url)
    assert await GoogleAdapter().fetch_detail(client, {}, job) is GONE
