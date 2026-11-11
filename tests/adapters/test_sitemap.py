import httpx
import pytest

from app.adapters.base import ParseError
from app.adapters.sitemap import SitemapUrl, read_urlset
from tests.conftest import load_fixture


async def test_reads_both_namespaces(client, mock):
    mock.get("https://careers.wipro.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=load_fixture("successfactors", "wipro_sitemap"))
    )
    mock.get("https://jobs.sap.com/en/jobs/sitemap.xml").mock(
        return_value=httpx.Response(200, content=load_fixture("sitemap_partial", "sap_sitemap"))
    )
    wipro = await read_urlset(client, "https://careers.wipro.com/sitemap.xml")
    sap = await read_urlset(client, "https://jobs.sap.com/en/jobs/sitemap.xml")
    assert len(wipro) == len(sap) == 25
    assert wipro[0] == SitemapUrl(
        "https://careers.wipro.com/job/Pune-SOLUTION-ARCHITECT-L1%28CONTRACT%29-IND-411005/1363531455/",
        "2026-11-07",
    )
    assert sap[0].loc.startswith("https://jobs.sap.com/en/jobs/") and sap[0].lastmod


async def test_sitemap_index_raises_parse_error(client, mock):
    mock.get("https://jobs.sap.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=load_fixture("sitemap_partial", "sap_index"))
    )
    with pytest.raises(ParseError):
        await read_urlset(client, "https://jobs.sap.com/sitemap.xml")


async def test_html_raises_parse_error(client, mock):
    mock.get("https://x.example/sitemap.xml").mock(
        return_value=httpx.Response(200, content=b"<!doctype html><html><body>hi</body></html>")
    )
    with pytest.raises(ParseError):
        await read_urlset(client, "https://x.example/sitemap.xml")


async def test_http_error_raises(client, mock):
    mock.get("https://x.example/sitemap.xml").mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        await read_urlset(client, "https://x.example/sitemap.xml")


async def test_entries_without_loc_are_skipped(client, mock):
    body = load_fixture("successfactors", "wipro_sitemap")
    first_loc = body.index(b"<loc>")
    end = body.index(b"</loc>", first_loc) + len(b"</loc>")
    mock.get("https://careers.wipro.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=body[:first_loc] + body[end:])
    )
    entries = await read_urlset(client, "https://careers.wipro.com/sitemap.xml")
    assert len(entries) == 24 and all(e.loc for e in entries)
