"""Keeps Gemini usage well under the free-tier limits.

- At most `rpm` requests in any 60 s window.
- At most `daily_cap` requests per Pacific-time day (Google resets quotas at midnight PT).
- A busy answer (503 "high demand") pauses for 2 minutes, with no other effect.
- A 429 pauses for 2 minutes. A second 429 on the same day stops for the day and
  learns a lower daily cap (60% of what that day managed) for the days after.
"""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from app.core.models import LlmUsage, Setting

PACIFIC = ZoneInfo("America/Los_Angeles")
PAUSE = timedelta(seconds=120)
LEARNED_KEY = "gemini_learned_cap"


def _now() -> datetime:
    return datetime.now(UTC)


class Pacer:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        rpm: int,
        daily_cap: int,
        clock: Callable[[], datetime] = _now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._sf = session_factory
        self.rpm = rpm
        self.daily_cap = daily_cap
        self._clock = clock
        self._sleep = sleep
        self._recent: deque[datetime] = deque()
        self._pause_until: datetime | None = None
        self._strikes: dict[date, int] = {}

    def _day(self, now: datetime) -> date:
        return now.astimezone(PACIFIC).date()

    async def acquire(self) -> bool:
        now = self._clock()
        if self._pause_until and now < self._pause_until:
            await self._sleep((self._pause_until - now).total_seconds())
            now = self._clock()
        while self._recent and now - self._recent[0] >= timedelta(seconds=60):
            self._recent.popleft()
        if len(self._recent) >= self.rpm:
            wait = (self._recent[0] + timedelta(seconds=60) - now).total_seconds()
            await self._sleep(wait)
            now = self._clock()
            self._recent.popleft()
        # No awaits below: the usage row is read, checked and committed in one go.
        with self._sf() as s:
            row = self._usage(s, self._day(now))
            if row.requests >= self._cap(s, row):
                s.commit()
                return False
            row.requests += 1
            s.commit()
        self._recent.append(now)
        return True

    def on_busy(self) -> None:
        self._pause_until = self._clock() + PAUSE

    def on_rate_limited(self) -> None:
        now = self._clock()
        day = self._day(now)
        self._pause_until = now + PAUSE
        self._strikes[day] = self._strikes.get(day, 0) + 1
        if self._strikes[day] < 2:
            return
        with self._sf() as s:
            row = self._usage(s, day)
            row.effective_cap = row.requests
            learned = max(10, int(row.requests * 0.6))
            setting = s.get(Setting, LEARNED_KEY)
            if setting is None:
                s.add(Setting(key=LEARNED_KEY, value={"cap": learned}))
            else:
                setting.value = {"cap": min(learned, setting.value.get("cap", learned))}
            s.commit()

    def _cap(self, s: Session, row: LlmUsage) -> int:
        caps = [self.daily_cap]
        if row.effective_cap is not None:
            caps.append(row.effective_cap)
        learned = s.get(Setting, LEARNED_KEY)
        if learned is not None:
            caps.append(int(learned.value["cap"]))
        return min(caps)

    def _usage(self, s: Session, day: date) -> LlmUsage:
        row = s.get(LlmUsage, day)
        if row is None:
            row = LlmUsage(day=day, requests=0, tokens=0)
            s.add(row)
            s.flush()
        return row
