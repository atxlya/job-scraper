import math
import re

import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
from app.adapters.company.apple import AppleAdapter, hydration
from tests.conftest import load_fixture

CFG = {"locale": "en-in", "team": "internships-STDNT-INTRN"}
SEARCH = "https://jobs.apple.com/en-in/search"
DETAIL = (
    "https://jobs.apple.com/en-in/details/200691891-3715/global-sourcing-and-supply-manager-intern"
)


def page(name):
    return httpx.Response(
        200, content=load_fixture("apple", name), headers={"content-type": "text/html"}
    )


async def test_parses_hydration_listing(client, mock):
    mock.get(SEARCH).mock(return_value=page("search_newest"))
    res = await AppleAdapter().list_jobs(client, CFG, "incremental")
    data = hydration(load_fixture("apple", "search_newest").decode())["search"]
    first = data["searchResults"][0]
    assert len(res.jobs) == len(data["searchResults"]) == 20
    assert res.reported_total == data["totalRecords"] == 130
    j = res.jobs[0]
    assert j.external_id == first["id"]
    assert j.title == first["postingTitle"]
    assert (
        j.url
        == f"https://jobs.apple.com/en-in/details/{first['id']}/{first['transformedPostingTitle']}"
    )
    assert j.platform_flags == {"intern": True}
    assert j.posted_at.isoformat().startswith(first["postDateInGMT"][:19])
    assert j.locations and j.country_codes


async def test_shanghai_location_from_name_and_country_id(client, mock):
    mock.get(SEARCH).mock(return_value=page("search_p1"))
    res = await AppleAdapter().list_jobs(client, CFG, "incremental")
    sh = next(j for j in res.jobs if j.external_id == "200691891-3715")
    assert sh.locations == ["Shanghai, China"] and sh.country_codes == ["CN"]


async def test_incremental_reads_newest_page_one(client, mock):
    route = mock.get(SEARCH).mock(return_value=page("search_newest"))
    res = await AppleAdapter().list_jobs(client, CFG, "incremental")
    assert len(route.calls) == 1 and res.complete is False
    assert route.calls.last.request.url.params["sort"] == "newest"


async def test_full_reads_all_pages(client, mock):
    def respond(request):
        return page("search_p1" if request.url.params["page"] == "1" else "search_p2")

    route = mock.get(SEARCH).mock(side_effect=respond)
    res = await AppleAdapter().list_jobs(client, CFG, "full")
    pages = [int(c.request.url.params["page"]) for c in route.calls]
    assert pages == list(range(1, math.ceil(130 / 20) + 1))
    assert res.complete is True


async def test_detail_text_to_html(client, mock):
    mock.get(DETAIL).mock(return_value=page("detail"))
    job = RawJob(external_id="200691891-3715", title="x", url=DETAIL)
    got = await AppleAdapter().fetch_detail(client, CFG, job)
    assert "<h3>Minimum qualifications</h3>" in got.description_html
    assert "<h3>Responsibilities</h3>" in got.description_html
    texts = re.findall(r">([^<]*)<", got.description_html)
    assert not [t for t in texts if "\n" in t and t.strip()]  # plain-text newlines became tags
    assert got.employment_type == "Intern" and got.apply_url == DETAIL


async def test_detail_missing_is_gone(client, mock):
    url = "https://jobs.apple.com/en-in/details/000000000-0000/missing"
    mock.get(url).mock(return_value=page("missing"))
    job = RawJob(external_id="000000000-0000", title="x", url=url)
    assert await AppleAdapter().fetch_detail(client, CFG, job) is GONE


async def test_page_without_hydration_raises_parse_error(client, mock):
    mock.get(SEARCH).mock(return_value=httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(ParseError):
        await AppleAdapter().list_jobs(client, CFG, "full")


def _with_details(details) -> httpx.Response:
    """The recorded job page, with its jobDetails route data replaced."""
    import json  # noqa: PLC0415

    text = load_fixture("apple", "detail").decode()
    loader = hydration(text)
    loader["jobDetails"] = details
    inner = json.dumps(json.dumps({"loaderData": loader}))
    text = re.sub(
        r'(window\.__staticRouterHydrationData\s*=\s*JSON\.parse\()(".*?")(\);)',
        lambda m: m.group(1) + inner + m.group(3),
        text,
        count=1,
        flags=re.S,
    )
    return httpx.Response(200, text=text, headers={"content-type": "text/html"})


async def test_detail_with_changed_shape_raises_parse_error(client, mock):
    mock.get(DETAIL).mock(return_value=_with_details({}))
    job = RawJob(external_id="200691891-3715", title="x", url=DETAIL)
    with pytest.raises(ParseError):
        await AppleAdapter().fetch_detail(client, CFG, job)
