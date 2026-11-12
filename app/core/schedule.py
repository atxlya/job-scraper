"""When the worker runs each job (docs/DESIGN.md §3 Schedule). Shared with the dashboard."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = "Asia/Kolkata"
INCREMENTAL_MINUTES = 30
FULL_AT = time(2, 0)  # nightly full sweep, IST
TRACKED_AT = time(4, 0)  # daily re-check of liked/applied jobs, IST


def next_full_at(at: datetime) -> datetime:
    """The next nightly full sweep after `at`."""
    tz = ZoneInfo(TZ)
    local = at.astimezone(tz)
    run = datetime.combine(local.date(), FULL_AT, tz)
    return run if run > local else run + timedelta(days=1)
