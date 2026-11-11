import pytest

from app.http.robots import Robots

NVIDIA = """User-agent: *
Disallow: /
Allow: /$
Allow: /careers
Allow: /api/pcsx
"""


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("/api/pcsx/search?domain=nvidia.com", True),
        ("/careers/job/123", True),
        ("/", True),
        ("/secret", False),
    ],
)
def test_longest_match_wins(path, allowed):
    assert Robots.parse(NVIDIA).allowed("job-scraper", path) is allowed


def test_wildcard_query_pattern():
    r = Robots.parse("User-agent: *\nDisallow: /*/jobs/results?*&page=\n")
    base = "/about/careers/applications/jobs/results"
    assert r.allowed("job-scraper", base + "?q=&target_level=INTERN") is True
    assert r.allowed("job-scraper", base + "?q=&page=2") is False


def test_specific_agent_group_overrides_star():
    r = Robots.parse("User-agent: LinkedInBot\nAllow: /v1/\n\nUser-agent: *\nDisallow: /\n")
    assert r.allowed("job-scraper", "/v1/companies/X") is False
    assert r.allowed("LinkedInBot", "/v1/companies/X") is True


def test_empty_allows_everything():
    assert Robots.parse("").allowed("job-scraper", "/anything") is True


def test_tie_prefers_allow():
    r = Robots.parse("User-agent: *\nDisallow: /a\nAllow: /a\n")
    assert r.allowed("job-scraper", "/a") is True


AMD = "User-agent: *\nAllow: /\nSitemap: http://careers.amd.com/sitemap.xml\ncrawl-delay: 5\n"


def test_crawl_delay_parsed():
    assert Robots.parse(AMD).crawl_delay("job-scraper/0.1") == 5.0
    assert Robots.parse("User-agent: *\nAllow: /\n").crawl_delay("job-scraper/0.1") is None
    assert Robots.parse("User-agent: *\nCrawl-delay: soon\n").crawl_delay("x/1") is None


def test_crawl_delay_follows_agent_group():
    text = "User-agent: job-scraper\nCrawl-delay: 2\n\nUser-agent: *\nCrawl-delay: 9\n"
    assert Robots.parse(text).crawl_delay("job-scraper/0.1") == 2.0
    assert Robots.parse(text).crawl_delay("otherbot/1") == 9.0
