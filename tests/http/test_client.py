import httpx
import pytest
import respx

from app.http.client import USER_AGENT, PoliteClient, RobotsDisallowed


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


@pytest.fixture
def ft():
    return FakeTime()


@pytest.fixture
def client(ft):
    return PoliteClient(min_interval_s=2.5, user_agent=USER_AGENT, clock=ft.clock, sleep=ft.sleep)


def robots(mock, host, body="User-agent: *\nAllow: /\n", status=200):
    return mock.get(f"https://{host}/robots.txt").mock(
        return_value=httpx.Response(status, text=body)
    )


@respx.mock
async def test_disallowed_url_never_requested(client):
    robots(respx, "a.com", "User-agent: *\nDisallow: /private\n")
    route = respx.get("https://a.com/private/x").mock(return_value=httpx.Response(200))
    with pytest.raises(RobotsDisallowed):
        await client.get("https://a.com/private/x")
    assert route.call_count == 0


@respx.mock
async def test_robots_cached_24h(client):
    r = robots(respx, "a.com")
    respx.get("https://a.com/1").mock(return_value=httpx.Response(200))
    respx.get("https://a.com/2").mock(return_value=httpx.Response(200))
    await client.get("https://a.com/1")
    await client.get("https://a.com/2")
    assert r.call_count == 1


@respx.mock
async def test_missing_robots_allows(client):
    robots(respx, "a.com", "", status=404)
    route = respx.get("https://a.com/x").mock(return_value=httpx.Response(200))
    await client.get("https://a.com/x")
    assert route.call_count == 1


@respx.mock
async def test_min_interval_per_host(client, ft):
    robots(respx, "a.com")
    robots(respx, "b.com")
    respx.get("https://a.com/x").mock(return_value=httpx.Response(200))
    respx.get("https://b.com/x").mock(return_value=httpx.Response(200))
    await client.get("https://a.com/x")
    await client.get("https://b.com/x")
    assert ft.sleeps == []
    await client.get("https://a.com/x")
    assert ft.sleeps and ft.sleeps[-1] >= 2.5


@respx.mock
async def test_retries_429_then_ok(client, ft):
    robots(respx, "a.com")
    respx.get("https://a.com/x").mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200)]
    )
    resp = await client.get("https://a.com/x")
    assert resp.status_code == 200
    assert max(ft.sleeps) >= 3


@respx.mock
async def test_gives_up_after_4_retries(client):
    robots(respx, "a.com")
    route = respx.get("https://a.com/x").mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await client.get("https://a.com/x")
    assert route.call_count == 5


@respx.mock
async def test_timeout_retried(client):
    robots(respx, "a.com")
    respx.get("https://a.com/x").mock(side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200)])
    assert (await client.get("https://a.com/x")).status_code == 200


@respx.mock
async def test_404_returned_not_raised(client):
    robots(respx, "a.com")
    respx.get("https://a.com/x").mock(return_value=httpx.Response(404))
    assert (await client.get("https://a.com/x")).status_code == 404


@respx.mock
async def test_user_agent_sent(client):
    robots(respx, "a.com")
    route = respx.get("https://a.com/x").mock(return_value=httpx.Response(200))
    await client.get("https://a.com/x")
    assert route.calls.last.request.headers["user-agent"] == USER_AGENT
    assert USER_AGENT == "job-scraper/0.1 (personal, non-commercial; respects robots.txt)"


@respx.mock
async def test_post_json_checks_robots(client):
    robots(respx, "a.com", "User-agent: *\nDisallow: /api\n")
    route = respx.post("https://a.com/api/jobs").mock(return_value=httpx.Response(200))
    with pytest.raises(RobotsDisallowed):
        await client.post_json("https://a.com/api/jobs", {"q": 1})
    assert route.call_count == 0


@respx.mock
async def test_html_robots_treated_as_no_rules(client):
    respx.get("https://a.com/robots.txt").mock(
        return_value=httpx.Response(
            200, text="<html>Disallow: /</html>", headers={"content-type": "text/html"}
        )
    )
    route = respx.get("https://a.com/x").mock(return_value=httpx.Response(200))
    await client.get("https://a.com/x")
    assert route.call_count == 1


@respx.mock
async def test_robots_server_error_blocks(client):
    robots(respx, "a.com", "", status=503)
    route = respx.get("https://a.com/x").mock(return_value=httpx.Response(200))
    with pytest.raises(RobotsDisallowed):
        await client.get("https://a.com/x")
    assert route.call_count == 0


@respx.mock
async def test_client_uses_longest_match(client):
    robots(respx, "a.com", "User-agent: *\nDisallow: /\nAllow: /api/pcsx\n")
    route = respx.get("https://a.com/api/pcsx/search").mock(return_value=httpx.Response(200))
    await client.get("https://a.com/api/pcsx/search", params={"domain": "x"})
    assert route.call_count == 1


@respx.mock
async def test_robots_transient_error_retried(client):
    respx.get("https://a.com/robots.txt").mock(
        side_effect=[httpx.ReadTimeout(""), httpx.Response(200, text="User-agent: *\n")]
    )
    route = respx.get("https://a.com/x").mock(return_value=httpx.Response(200))
    await client.get("https://a.com/x")
    assert route.call_count == 1


@respx.mock
async def test_robots_unreachable_message_names_error(client):
    respx.get("https://a.com/robots.txt").mock(side_effect=httpx.ReadTimeout(""))
    with pytest.raises(RobotsDisallowed, match="ReadTimeout"):
        await client.get("https://a.com/x")


@respx.mock
async def test_client_waits_for_crawl_delay(ft):
    c = PoliteClient(min_interval_s=1, user_agent=USER_AGENT, clock=ft.clock, sleep=ft.sleep)
    robots(respx, "amd.com", "User-agent: *\nAllow: /\ncrawl-delay: 5\n")
    respx.get("https://amd.com/a").mock(return_value=httpx.Response(200))
    await c.get("https://amd.com/a")
    await c.get("https://amd.com/a")
    assert ft.sleeps == [5]


@respx.mock
async def test_crawl_delay_capped(ft):
    c = PoliteClient(min_interval_s=1, user_agent=USER_AGENT, clock=ft.clock, sleep=ft.sleep)
    robots(respx, "slow.com", "User-agent: *\nCrawl-delay: 3600\n")
    respx.get("https://slow.com/a").mock(return_value=httpx.Response(200))
    await c.get("https://slow.com/a")
    await c.get("https://slow.com/a")
    assert ft.sleeps == [30]


@respx.mock
async def test_redirect_target_checked_against_robots(client):
    robots(respx, "a.com", "User-agent: *\nDisallow: /error\n")
    respx.get("https://a.com/job/x/1/").mock(
        return_value=httpx.Response(302, headers={"Location": "/errorpage/?errortype=Exception"})
    )
    target = respx.get("https://a.com/errorpage/").mock(return_value=httpx.Response(200))
    with pytest.raises(RobotsDisallowed):
        await client.get("https://a.com/job/x/1/")
    assert target.call_count == 0


@respx.mock
async def test_allowed_redirect_followed(client):
    robots(respx, "a.com")
    respx.get("https://a.com/job/A/1340802255/").mock(
        return_value=httpx.Response(302, headers={"Location": "/job/A/134372-en_US/"})
    )
    respx.get("https://a.com/job/A/134372-en_US/").mock(return_value=httpx.Response(200, text="ok"))
    resp = await client.get("https://a.com/job/A/1340802255/")
    assert resp.status_code == 200
    assert str(resp.url).endswith("134372-en_US/")


@respx.mock
async def test_follow_redirects_false_returns_3xx(client):
    robots(respx, "a.com")
    respx.get("https://a.com/job/x/1/").mock(
        return_value=httpx.Response(302, headers={"Location": "/errorpage/?errortype=Exception"})
    )
    target = respx.get("https://a.com/errorpage/").mock(return_value=httpx.Response(200))
    resp = await client.get("https://a.com/job/x/1/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/errorpage/?errortype=Exception"
    assert target.call_count == 0


@respx.mock
async def test_redirect_to_other_host_uses_its_robots(client):
    robots(respx, "a.com")
    robots(respx, "b.com", "User-agent: *\nDisallow: /y\n")
    respx.get("https://a.com/x").mock(
        return_value=httpx.Response(302, headers={"Location": "https://b.com/y"})
    )
    target = respx.get("https://b.com/y").mock(return_value=httpx.Response(200))
    with pytest.raises(RobotsDisallowed):
        await client.get("https://a.com/x")
    assert target.call_count == 0


@respx.mock
async def test_too_many_redirects(client):
    robots(respx, "a.com")
    for i in range(6):
        respx.get(f"https://a.com/r{i}").mock(
            return_value=httpx.Response(302, headers={"Location": f"/r{i + 1}"})
        )
    with pytest.raises(httpx.TooManyRedirects):
        await client.get("https://a.com/r0")


@respx.mock
async def test_robots_redirect_still_followed(client):
    respx.get("https://a.com/robots.txt").mock(
        return_value=httpx.Response(301, headers={"Location": "/robots-real.txt"})
    )
    respx.get("https://a.com/robots-real.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
    )
    route = respx.get("https://a.com/private/x").mock(return_value=httpx.Response(200))
    with pytest.raises(RobotsDisallowed):
        await client.get("https://a.com/private/x")
    assert route.call_count == 0


@respx.mock
async def test_post_form_sends_urlencoded_and_checks_robots(client):
    robots(respx, "a.com", "User-agent: *\nDisallow: /private\n")
    route = respx.post("https://a.com/x").mock(return_value=httpx.Response(200))
    blocked = respx.post("https://a.com/private/y").mock(return_value=httpx.Response(200))
    resp = await client.post_form("https://a.com/x", {"a": "1 2", "b": "w+c/="})
    assert resp.status_code == 200
    sent = route.calls[0].request
    assert sent.headers["content-type"] == "application/x-www-form-urlencoded"
    assert sent.content == b"a=1+2&b=w%2Bc%2F%3D"
    with pytest.raises(RobotsDisallowed):
        await client.post_form("https://a.com/private/y", {})
    assert blocked.call_count == 0
