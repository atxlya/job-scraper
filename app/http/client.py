"""One HTTP client for every scraper: robots.txt, per-host pacing, retries."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from app.http.robots import Robots

log = logging.getLogger(__name__)

USER_AGENT = "job-scraper/0.1 (personal, non-commercial; respects robots.txt)"
ROBOTS_TTL_S = 24 * 3600
MAX_RETRIES = 4
MAX_CRAWL_DELAY_S = 30.0  # a typo like "Crawl-delay: 3600" must not stall a source
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_REDIRECTS = 5


class RobotsDisallowed(Exception):
    """robots.txt does not allow this URL (or robots.txt could not be read)."""


class RobotsUnavailable(RobotsDisallowed):
    """robots.txt couldn't be read (network error or 5xx), so nothing is fetched for now.

    A subclass, so code that stops on RobotsDisallowed still stops; the dashboard
    uses it to say "couldn't reach the site" instead of "robots.txt doesn't allow it".
    """


class PoliteClient:
    def __init__(
        self,
        min_interval_s: float,
        user_agent: str = USER_AGENT,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 20.0,
    ):
        self.min_interval_s = min_interval_s
        self.user_agent = user_agent
        self._clock = clock
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout_s,
            follow_redirects=False,  # _request follows hops itself, robots-checking each
            max_redirects=MAX_REDIRECTS,  # only robots.txt fetches follow redirects here
            transport=transport,
        )
        self._robots: dict[str, tuple[float, Robots]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    async def get(
        self, url: str, *, params=None, headers=None, follow_redirects: bool = True
    ) -> httpx.Response:
        return await self._request(
            "GET", url, follow_redirects=follow_redirects, params=params, headers=headers
        )

    async def post_json(
        self, url: str, json: dict, *, headers=None, follow_redirects: bool = True
    ) -> httpx.Response:
        return await self._request(
            "POST", url, follow_redirects=follow_redirects, json=json, headers=headers
        )

    async def post_form(
        self, url: str, data: dict[str, str], *, headers=None, follow_redirects: bool = True
    ) -> httpx.Response:
        """application/x-www-form-urlencoded POST (WebForms postbacks, RippleHire)."""
        return await self._request(
            "POST", url, follow_redirects=follow_redirects, data=data, headers=headers
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(
        self, method: str, url: str, *, follow_redirects: bool = True, **kw
    ) -> httpx.Response:
        """Send a request; follow redirects here so every hop is robots-checked and paced."""
        request = self._http.build_request(method, url, **kw)
        hops = 0
        while True:
            resp = await self._send_one(request)
            if not follow_redirects or resp.next_request is None:
                return resp
            hops += 1
            if hops > MAX_REDIRECTS:
                raise httpx.TooManyRedirects(
                    f"exceeded {MAX_REDIRECTS} redirects", request=resp.request
                )
            request = resp.next_request

    async def _send_one(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        method = request.method
        robots = await self._check_robots(url)
        delay = robots.crawl_delay(self.user_agent) or 0.0
        interval = min(MAX_CRAWL_DELAY_S, max(self.min_interval_s, delay))
        host = request.url.netloc.decode()
        lock = self._locks.setdefault(host, asyncio.Lock())
        attempt = 0
        while True:
            async with lock:
                await self._wait_turn(host, interval)
                try:
                    resp = await self._http.send(request)
                    err: Exception | None = None
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    resp, err = None, e
                finally:
                    self._last[host] = self._clock()
            retryable = err is not None or resp.status_code in RETRY_STATUSES
            if not retryable:
                return resp
            if attempt >= MAX_RETRIES:
                if err is not None:
                    raise err
                resp.raise_for_status()
            delay = min(60.0, 2.0**attempt) + random.uniform(0, 1)
            if resp is not None and (ra := resp.headers.get("Retry-After", "")).isdigit():
                delay = max(delay, float(ra))
            log.info("retry %s %s in %.1fs (attempt %d)", method, url, delay, attempt + 1)
            await self._sleep(delay)
            attempt += 1

    async def _wait_turn(self, host: str, interval: float) -> None:
        last = self._last.get(host)
        if last is not None:
            wait = last + interval - self._clock()
            if wait > 0:
                await self._sleep(wait)

    async def _check_robots(self, url: str) -> Robots:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(base)
        if cached is None or self._clock() - cached[0] > ROBOTS_TTL_S:
            parser = await self._fetch_robots(base)
            self._robots[base] = (self._clock(), parser)
            cached = self._robots[base]
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        if not cached[1].allowed(self.user_agent, path):
            raise RobotsDisallowed(url)
        return cached[1]

    async def _fetch_robots(self, base: str) -> Robots:
        """RFC 9309: 4xx means no rules; 5xx or network failure means stop for now."""
        resp = None
        for attempt in range(3):
            try:
                resp = await self._http.get(f"{base}/robots.txt", follow_redirects=True)
                break
            except httpx.TooManyRedirects as e:
                # RFC 9309 needs at least five hops followed; past that, fetch nothing.
                raise RobotsUnavailable(
                    f"robots.txt for {base}: more than {MAX_REDIRECTS} redirects"
                ) from e
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise RobotsUnavailable(
                        f"robots.txt unreachable for {base}: {type(e).__name__} {e}".strip()
                    ) from e
                await self._sleep(2.0 * (attempt + 1))
        if resp.status_code >= 500:
            raise RobotsUnavailable(f"robots.txt returned {resp.status_code} for {base}")
        if resp.status_code >= 400 or "text/html" in resp.headers.get("content-type", ""):
            return Robots.parse("")
        return Robots.parse(resp.text)
