"""When the worker runs each job (docs/DESIGN.md §3 Schedule). Shared with the dashboard.

The times can be changed on the dashboard's Sources page. They are saved in the `settings`
table; the worker re-reads them every minute and moves its jobs, so no restart is needed.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.models import Setting

TZ = "Asia/Kolkata"
SCHEDULE_KEY = "schedule"
MIN_INCREMENTAL, MAX_INCREMENTAL = 15, 360  # minutes; faster only hits 100+ sites harder
MIN_GAP = timedelta(hours=1)  # full sweep and tracked re-check must not start together


class ScheduleError(ValueError):
    """A schedule the worker won't run; the message is shown on the dashboard."""


@dataclass(frozen=True)
class ScheduleConfig:
    incremental_minutes: int  # quick check every N minutes
    full_at: time  # nightly full sweep, IST
    tracked_at: time  # daily re-check of liked/applied jobs, IST

    def check(self) -> None:
        n = self.incremental_minutes
        if n < MIN_INCREMENTAL:
            raise ScheduleError(f"The quick check must be at least {MIN_INCREMENTAL} min apart.")
        if n > MAX_INCREMENTAL:
            raise ScheduleError(f"The quick check must be at most {MAX_INCREMENTAL} min apart.")
        a = self.full_at.hour * 60 + self.full_at.minute
        b = self.tracked_at.hour * 60 + self.tracked_at.minute
        gap = abs(a - b) % 1440
        if min(gap, 1440 - gap) < MIN_GAP.total_seconds() / 60:
            raise ScheduleError(
                "The full sweep and the tracked re-check must be at least an hour apart."
            )


DEFAULT = ScheduleConfig(30, time(2, 0), time(4, 0))


def _hhmm(t: time) -> str:
    return t.strftime("%H:%M")


def load_schedule(s: Session) -> ScheduleConfig:
    """The saved schedule, or the default if none is saved or the row can't be used."""
    row = s.get(Setting, SCHEDULE_KEY)
    if row is None:
        return DEFAULT
    try:
        v = row.value
        cfg = ScheduleConfig(
            int(v["incremental_minutes"]),
            time.fromisoformat(v["full_at"]),
            time.fromisoformat(v["tracked_at"]),
        )
        cfg.check()
    except (KeyError, TypeError, ValueError):
        return DEFAULT
    return cfg


def save_schedule(s: Session, cfg: ScheduleConfig) -> None:
    cfg.check()
    value = {
        "incremental_minutes": cfg.incremental_minutes,
        "full_at": _hhmm(cfg.full_at),
        "tracked_at": _hhmm(cfg.tracked_at),
    }
    row = s.get(Setting, SCHEDULE_KEY)
    if row is None:
        s.add(Setting(key=SCHEDULE_KEY, value=value))
    else:
        row.value = value


def next_daily(at: datetime, when: time) -> datetime:
    """The next time the clock in IST reads `when`, after `at`."""
    tz = ZoneInfo(TZ)
    local = at.astimezone(tz)
    run = datetime.combine(local.date(), when, tz)
    return run if run > local else run + timedelta(days=1)
