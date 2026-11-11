import re
from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.base import GONE, ParseError
from app.adapters.successfactors import SuccessFactorsAdapter
from tests.conftest import load_fixture

ROBOTS = """User-agent: *
Disallow: /applybutton/
Disallow: /talentcommunity/
Disallow: /mobile/talentcommunity/
Disallow: /emailsubscribe/
Disallow: /email/image/
Disallow: /services/
Disallow: /preapply/
Disallow: /error
Disallow: /unsubscribe/
Disallow: /reset/
"""

HOSTS = [
    "careers.wipro.com",
    "careers.hcltech.com",
    "careers.ey.com",
    "southasiacareers.deloitte.com",
]


@pytest.fixture(autouse=True)
def sf_robots(mock):
    for host in HOSTS:
        mock.get(f"https://{host}/robots.txt").mock(return_value=httpx.Response(200, text=ROBOTS))


def serve_sitemap(mock, host, name):
    body = load_fixture("successfactors", name)
    mock.get(f"https://{host}/sitemap.xml").mock(return_value=httpx.Response(200, content=body))
    return body


def serve_html(mock, url, name):
    return mock.get(url).mock(
        return_value=httpx.Response(200, content=load_fixture("successfactors", name))
    )


def listed(host, url):
    from app.adapters.base import RawJob

    return RawJob(external_id=url.rstrip("/").rsplit("/", 1)[1], title="x", url=url)


async def test_parses_sitemap(client, mock):
    serve_sitemap(mock, "careers.wipro.com", "wipro_sitemap")
    cfg = {"host": "careers.wipro.com"}
    res = await SuccessFactorsAdapter().list_jobs(client, cfg, "full")
    assert len(res.jobs) == 25
    j = res.jobs[0]
    assert j.external_id == "1363531455"
    assert j.title == "Pune SOLUTION ARCHITECT L1(CONTRACT) IND 411005"
    assert j.title_from_url is True
    assert res.reported_total is None
    assert res.complete is True
    inc = await SuccessFactorsAdapter().list_jobs(client, cfg, "incremental")
    assert inc.complete is False


async def test_ey_keeps_other_site_paths(client, mock):
    cfg = {"host": "careers.ey.com"}
    body = serve_sitemap(mock, "careers.ey.com", "ey_sitemap")
    res = await SuccessFactorsAdapter().list_jobs(client, cfg, "full")
    assert len(res.jobs) == len(re.findall(rb"<loc>", body))
    sgv = serve_sitemap(mock, "careers.ey.com", "ey_sitemap_sgv")
    res = await SuccessFactorsAdapter().list_jobs(client, cfg, "full")
    assert len(res.jobs) == len(re.findall(rb"<loc>", sgv)) > 0
    assert all("/sgv/job/" in j.url for j in res.jobs)


async def test_other_urls_are_skipped(client, mock):
    body = (
        b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<url><loc>https://careers.wipro.com/search/</loc></url>"
        b"<url><loc>https://other.example.com/job/A-B/123/</loc></url>"
        b"<url><loc>https://careers.wipro.com/job/A-B/123/</loc></url></urlset>"
    )
    mock.get("https://careers.wipro.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=body)
    )
    res = await SuccessFactorsAdapter().list_jobs(client, {"host": "careers.wipro.com"}, "full")
    assert [j.external_id for j in res.jobs] == ["123"]


async def test_detail_microdata(client, mock):
    url = "https://southasiacareers.deloitte.com/job/Noida-Intern-Talent-Acquisition-Noida-Talent/61228644/"
    serve_html(mock, url, "deloitte_job")
    job = listed("", url)
    out = await SuccessFactorsAdapter().fetch_detail(client, {}, job)
    assert out.title == "Intern | Talent Acquisition | Noida | Talent"
    assert out.posted_at == datetime(2026, 11, 3, tzinfo=UTC)
    assert out.locations == ["Noida, IN"]
    assert out.country_codes == ["IN"]
    assert "Requirement is for an Intern in Operate Hiring Team." in out.description_html
    assert out.title_from_url is False
    assert out.apply_url is None
    assert out.external_id == "61228644" and out.url == url


async def test_detail_country_from_street_address(client, mock):
    url = "https://careers.ey.com/ey/job/Belgrade-Quant-Intern-in-EY-Risk-Consulting-11070/1450762633/"
    serve_html(mock, url, "ey_job")
    out = await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", url))
    assert out.locations == ["Belgrade, RS, 11070"]
    assert out.country_codes == ["RS"]
    assert out.posted_at == datetime(2026, 10, 23, tzinfo=UTC)


async def test_detail_follows_allowed_redirect(client, mock):
    old = "https://careers.wipro.com/job/Bengaluru-Management-Trainee-IND-560035/1340802255/"
    new = "https://careers.wipro.com/job/Bengaluru-Management-Trainee-IND-560035/134372-en_US/"
    mock.get(old).mock(
        return_value=httpx.Response(
            302, headers={"Location": "/job/Bengaluru-Management-Trainee-IND-560035/134372-en_US/"}
        )
    )
    serve_html(mock, new, "wipro_job")
    out = await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", old))
    assert out.title == "Management Trainee"
    assert out.locations == ["Bengaluru, Karnataka"]
    assert out.country_codes == ["IN"]
    assert out.posted_at == datetime(2026, 10, 27, tzinfo=UTC)
    assert out.url == old and out.external_id == "1340802255"


async def test_detail_title_and_description_only(client, mock):
    url = "https://careers.hcltech.com/job/Trainee-Voice/150770-en_US/"
    serve_html(mock, url, "hcltech_job")
    out = await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", url))
    assert out.title == "Trainee-Voice"
    assert out.locations == []
    assert out.posted_at is None
    assert "handle calls" in out.description_html


async def test_missing_job_is_gone_without_fetching_error_page(client, mock):
    url = "https://careers.wipro.com/job/Gone-Job/999/"
    mock.get(url).mock(
        return_value=httpx.Response(302, headers={"Location": "/errorpage/?errortype=Exception"})
    )
    err = mock.get(url__regex=r"https://careers\.wipro\.com/errorpage/.*").mock(
        return_value=httpx.Response(200, text="error")
    )
    out = await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", url))
    assert out is GONE
    assert not err.called


async def test_second_hop_to_error_page_is_gone_without_fetching_it(client, mock):
    old = "https://careers.wipro.com/job/Gone-Job/999/"
    mid = "https://careers.wipro.com/job/Gone-Job/999-en_US/"
    mock.get(old).mock(
        return_value=httpx.Response(302, headers={"Location": "/job/Gone-Job/999-en_US/"})
    )
    mock.get(mid).mock(
        return_value=httpx.Response(302, headers={"Location": "/errorpage/?errortype=Exception"})
    )
    err = mock.get(url__regex=r"https://careers\.wipro\.com/errorpage/.*").mock(
        return_value=httpx.Response(200, text="error")
    )
    out = await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", old))
    assert out is GONE
    assert not err.called


async def test_endless_redirects_raise(client, mock):
    url = "https://careers.wipro.com/job/Loop/999/"
    mock.get(url).mock(return_value=httpx.Response(302, headers={"Location": url}))
    with pytest.raises(httpx.TooManyRedirects):
        await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", url))


@pytest.mark.parametrize("status", [404, 410])
async def test_404_and_410_are_gone(client, mock, status):
    url = "https://careers.wipro.com/job/Gone-Job/999/"
    mock.get(url).mock(return_value=httpx.Response(status))
    assert await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", url)) is GONE


async def test_server_error_raises(client, mock):
    url = "https://careers.wipro.com/job/Broken/999/"
    mock.get(url).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", url))


async def test_page_without_title_raises_parse_error(client, mock):
    url = "https://careers.hcltech.com/job/Trainee-Voice/150770-en_US/"
    mock.get(url).mock(
        return_value=httpx.Response(200, content=load_fixture("successfactors", "hcltech_sitemap"))
    )
    with pytest.raises(ParseError):
        await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", url))


async def test_redirect_without_location_raises(client, mock):
    url = "https://careers.wipro.com/job/Odd/999/"
    route = mock.get(url).mock(return_value=httpx.Response(302))
    with pytest.raises(ParseError, match="Location"):
        await SuccessFactorsAdapter().fetch_detail(client, {}, listed("", url))
    assert route.call_count == 1
