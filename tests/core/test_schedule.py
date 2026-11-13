from datetime import UTC, datetime, time

import pytest

from app.core.db import make_engine, make_session_factory
from app.core.models import Base, Setting
from app.core.schedule import (
    DEFAULT,
    SCHEDULE_KEY,
    ScheduleConfig,
    ScheduleError,
    load_schedule,
    next_daily,
    save_schedule,
)


@pytest.fixture
def sf(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(eng)
    return make_session_factory(eng)


def test_default_when_nothing_saved(sf):
    with sf() as s:
        assert load_schedule(s) == DEFAULT == ScheduleConfig(30, time(2, 0), time(4, 0))


def test_save_and_load(sf):
    cfg = ScheduleConfig(45, time(1, 30), time(5, 15))
    with sf() as s:
        save_schedule(s, cfg)
        s.commit()
    with sf() as s:
        assert load_schedule(s) == cfg
        save_schedule(s, DEFAULT)  # overwrites the row
        s.commit()
    with sf() as s:
        assert load_schedule(s) == DEFAULT


def test_broken_row_falls_back_to_default(sf):
    with sf() as s:
        s.add(Setting(key=SCHEDULE_KEY, value={"incremental_minutes": "x"}))
        s.commit()
        assert load_schedule(s) == DEFAULT


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        (ScheduleConfig(10, time(2), time(4)), "at least 15"),
        (ScheduleConfig(400, time(2), time(4)), "at most 360"),
        (ScheduleConfig(30, time(2), time(2, 30)), "an hour apart"),
        (ScheduleConfig(30, time(23, 30), time(0, 15)), "an hour apart"),  # across midnight
    ],
)
def test_rejected(cfg, message):
    with pytest.raises(ScheduleError, match=message):
        cfg.check()


def test_accepted_edges():
    ScheduleConfig(15, time(23, 30), time(0, 30)).check()
    ScheduleConfig(360, time(2), time(4)).check()


def test_next_daily():
    at = datetime(2026, 11, 11, 4, 30, tzinfo=UTC)  # 10:00 IST
    assert next_daily(at, time(2)) == datetime(2026, 11, 11, 20, 30, tzinfo=UTC)
    assert next_daily(at, time(11)) == datetime(2026, 11, 11, 5, 30, tzinfo=UTC)
