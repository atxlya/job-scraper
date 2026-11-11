"""The fixture recorder's XML trimming and its --no-follow flag."""

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest
import respx

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "record_fixture.py"
spec = importlib.util.spec_from_file_location("record_fixture", SCRIPT)
rf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rf)

SM = "http://www.sitemaps.org/schemas/sitemap/0.9"


def test_trim_xml_keeps_matching_items_up_to_max():
    xml = (
        f'<?xml version="1.0"?><urlset xmlns="{SM}">'
        + "".join(f"<url><loc>https://x/job/{n}/</loc></url>" for n in range(5))
        + "<url><loc>https://x/about/</loc></url></urlset>"
    ).encode()
    out = rf.trim_xml(xml, 2, r"/job/")
    assert out.count(b"<url>") == 2 and b"/about/" not in out
    assert f'xmlns="{SM}"'.encode() in out and b"ns0:" not in out


def test_trim_xml_nested_default_namespace_keeps_the_roots():
    other = "http://www.w3.org/1999/xhtml"
    xml = (
        f'<urlset xmlns="{SM}"><url><loc>https://x/job/1/</loc>'
        f'<link xmlns="{other}" rel="alternate"/></url></urlset>'
    ).encode()
    out = rf.trim_xml(xml, 5, "")
    assert f'<urlset xmlns="{SM}"'.encode() in out
    assert b"<loc>https://x/job/1/</loc>" in out and b"ns0:" not in out


def test_trim_xml_rss_and_other_xml():
    rss = b"<rss><channel><item><link>https://a/1</link></item><item><link>https://b/2</link></item></channel></rss>"
    assert rf.trim_xml(rss, 5, "a/").count(b"<item>") == 1
    feed = b"<feed><entry/></feed>"
    assert rf.trim_xml(feed, 1, "") == feed


@pytest.mark.parametrize("extra", [["--form", "a=1"], ["--json", "{}"]])
@respx.mock
async def test_no_follow_applies_to_post(monkeypatch, capsys, extra):
    respx.get("https://a.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.post("https://a.com/x").mock(
        return_value=httpx.Response(302, headers={"Location": "/error.aspx"})
    )
    target = respx.get("https://a.com/error.aspx").mock(return_value=httpx.Response(200))
    argv = ["record_fixture.py", "t", "n", "POST", "https://a.com/x", "--no-follow", *extra]
    monkeypatch.setattr(sys, "argv", argv)
    await rf.main()
    assert "302 Location: /error.aspx" in capsys.readouterr().out
    assert target.call_count == 0
