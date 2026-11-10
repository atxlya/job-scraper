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
RETRY_STATUSES = {429, 500, 502, 503, 504}


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
            follow_redirects=True,
            transport=transport,
        )
        self._robots: dict[str, tuple[float, Robots]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    async def get(self, url: str, *, params=None, headers=None) -> httpx.Response:
        return await self._request("GET", url, params=params, headers=headers)

    async def post_json(self, url: str, json: dict, *, headers=None) -> httpx.Response:
        return await self._request("POST", url, json=json, headers=headers)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        full = str(httpx.URL(url, params=kw.get("params")))
        await self._check_robots(full)
        host = urlsplit(url).netloc
        lock = self._locks.setdefault(host, asyncio.Lock())
        attempt = 0
        while True:
            async with lock:
                await self._wait_turn(host)
                try:
                    resp = await self._http.request(method, url, **kw)
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

    async def _wait_turn(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            wait = last + self.min_interval_s - self._clock()
            if wait > 0:
                await self._sleep(wait)

    async def _check_robots(self, url: str) -> None:
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

    async def _fetch_robots(self, base: str) -> Robots:
        """RFC 9309: 4xx means no rules; 5xx or network failure means stop for now."""
        resp = None
        for attempt in range(3):
            try:
                resp = await self._http.get(f"{base}/robots.txt")
                break
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
