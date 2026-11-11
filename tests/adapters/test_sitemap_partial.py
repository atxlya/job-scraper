import re

import httpx
import pytest

from app.adapters.base import RawJob
from app.adapters.sitemap_partial import SitemapPartialAdapter
from tests.conftest import load_fixture

COGNIZANT = {
    "sitemap": "https://careers.cognizant.com/sitemap.xml",
    "job_url": r"^https://careers\.cognizant\.com/global-en/jobs/(?P<id>\d+)/(?P<slug>[^/]+)/$",
}
SAP = {
    "sitemap": "https://jobs.sap.com/en/jobs/sitemap.xml",
    "job_url": r"^https://jobs\.sap\.com/en/jobs/(?P<id>\d+)/(?P<slug>[^/]+)/$",
}


@pytest.fixture(autouse=True)
def robots(mock):
    for host in ("careers.cognizant.com", "jobs.sap.com"):
        mock.get(f"https://{host}/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
        )


def serve(mock, cfg, name):
    body = load_fixture("sitemap_partial", name)
    mock.get(cfg["sitemap"]).mock(return_value=httpx.Response(200, content=body))
    return body.decode()


async def test_cognizant_keeps_global_en_jobs(client, mock):
    xml = serve(mock, COGNIZANT, "cognizant_sitemap")
    res = await SitemapPartialAdapter().list_jobs(client, COGNIZANT, "full")
    pattern = re.compile(COGNIZANT["job_url"])
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    assert any("/india-en/jobs/" in loc for loc in locs)  # the exclusion below is not vacuous
    ids = {m["id"] for loc in locs if (m := pattern.match(loc))}
    assert ids
    assert len(res.jobs) == len(ids)
    assert all(pattern.match(j.url) for j in res.jobs)
    assert not any("/india-en/" in j.url for j in res.jobs)
    assert res.reported_total is None


async def test_sap_titles_from_slug(client, mock):
    serve(mock, SAP, "sap_sitemap")
    res = await SitemapPartialAdapter().list_jobs(client, SAP, "full")
    job = next(j for j in res.jobs if j.external_id == "744000160974349")
    assert job.title == "Sap ixp intern technical support"
    assert job.platform_flags == {"partial": True}
    assert job.description_html is None
    assert job.title_from_url is False


async def test_duplicate_ids_kept_once(client, mock):
    xml = serve(mock, SAP, "sap_sitemap")
    first = re.search(r"<url>.*?</url>", xml).group(0)
    doubled = xml.replace("</urlset>", first + "</urlset>")
    assert doubled.count(first) == 2  # the duplicate really is in the sitemap
    mock.get(SAP["sitemap"]).mock(return_value=httpx.Response(200, content=doubled))
    once = await SitemapPartialAdapter().list_jobs(client, SAP, "full")
    mock.get(SAP["sitemap"]).mock(return_value=httpx.Response(200, content=xml))
    plain = await SitemapPartialAdapter().list_jobs(client, SAP, "full")
    ids = [j.external_id for j in once.jobs]
    assert len(ids) == len(set(ids)) == len(plain.jobs)


async def test_never_requests_job_pages(client, mock):
    cog = mock.get(url__regex=r"^https://careers\.cognizant\.com/global-en/jobs/.*")
    sap = mock.get(url__regex=r"^https://jobs\.sap\.com/en/jobs/\d+/.*")
    for url in (
        "https://careers.cognizant.com/global-en/jobs/45840/computer-science-graduate/",
        "https://jobs.sap.com/en/jobs/744000160974349/sap-ixp-intern-technical-support/",
    ):
        job = RawJob(external_id="1", title="x", url=url, platform_flags={"partial": True})
        assert await SitemapPartialAdapter().fetch_detail(client, {}, job) == job
    assert not cog.called
    assert not sap.called


async def test_complete_only_in_full(client, mock):
    serve(mock, SAP, "sap_sitemap")
    adapter = SitemapPartialAdapter()
    assert (await adapter.list_jobs(client, SAP, "full")).complete is True
    assert (await adapter.list_jobs(client, SAP, "incremental")).complete is False
