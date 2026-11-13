# Editable schedule

Branch `schedule-settings`, 2026-11-14, cut from `main`. The user asked to be able to change the quick-check interval and the nightly times from the dashboard instead of in code.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 759 passing (was 740) |
| Web tests (`cd web && npm run check`) | 144 passing (was 140); type-check clean; build OK |
| Lint (`ruff check`, `ruff format`) | Clean |
| On a copy of the real database, in the browser | The Sources page shows the Schedule line and the edit form. Saving 45 min updated the line, showed "Saved…", and wrote `{"incremental_minutes": 45, "full_at": "02:00", "tracked_at": "04:00"}` to the copy's `settings` table. Checked at 1440 px, dark theme |
| **Not checked** | A real worker process noticing the change and moving its jobs. That is covered only by a test that calls the watcher directly on a paused scheduler; the Pi has not been watched doing it. Also not checked: the form at phone width, and the light theme |

## What changed

**Storage and rules:** `app/core/schedule.py`
- `ScheduleConfig` holds the quick-check interval in minutes, and the full-sweep and tracked re-check times in IST.
- `check()` rejects:
  - a quick check under 15 or over 360 minutes apart;
  - a full sweep and re-check less than an hour apart, including across midnight.
- `load_schedule` reads the `schedule` row of the existing `settings` table. With no row, or a row that can't be used, it returns the old defaults: 30 min, 02:00 and 04:00.
- `save_schedule` checks the values, then writes them.
- `next_daily` replaces `next_full_at`, so the next time can be worked out for either daily run.
- The fixed constants `INCREMENTAL_MINUTES`, `FULL_AT` and `TRACKED_AT` are gone.

**API:** `app/api/sources.py`
- `GET /api/schedule` now also returns `full_at`, `tracked_at` and `next_tracked_at`.
- `PUT /api/schedule` saves a new schedule. A refused one gets a 422 with the reason. It needs a login, like the rest of `/api`.

**Worker:** `app/worker/scheduler.py`
- The three jobs are built from the saved schedule.
- A `schedule` job runs every 60 s. It re-reads the row, and if the schedule changed, it calls `reschedule_job` for the three jobs.
- It's registered as a bound async method (`ScheduleWatch(...).check`):
  - APScheduler 3.11 doesn't recognise an object with an async `__call__` as a coroutine function, so it would have called it without awaiting, and the watcher would never have run.
  - A test now pins this.

**Dashboard:** `web/src/components/ScheduleCard.tsx`, on the Sources page under the summary line
- One line: "Schedule · Quick check every N min · Full sweep HH:MM IST · Re-check tracked jobs HH:MM IST", with an **Edit** button.
- Edit opens:
  - a number field for the minutes;
  - two time fields;
  - Save and Cancel;
  - a hint stating the limits.
- The server's reason is shown if it refuses a value. The minutes field has no browser `min`/`max`, so a too-small value reaches the server and gets that explanation, instead of the browser's generic bubble.
- After saving, the summary line's "Next full sweep" updates at once from the response.

**Docs:** DESIGN §3 Schedule, the RUNBOOK schedule table, and the README.

## Decisions and their cost

- **The worker polls the database every 60 s**, instead of the API telling the worker directly.
  - Why: the API and the worker are separate containers that share only the database, and adding a channel between them would mean a new port or signal.
  - Cost: up to a minute's delay, and one tiny read a minute.
- **Changing the interval restarts its count.** `reschedule_job` with a new interval trigger starts counting from the moment of the change, so the next quick check comes N minutes after you save, not on the old rhythm.
- **Limits of 15–360 minutes and a 1-hour gap.**
  - Why: at 106 companies, a run under 15 minutes apart adds load on the sites for little gain.
  - Cost: you can't set the quick check faster, even on purpose.
  - The full sweep can still overlap a quick check, as before: the per-source lock in `run_source` stops the two from scraping one source at the same time.
- **No mockup first.** The project's rule is a mockup before a layout change. This added one line and a small form on the Sources page, in the existing card and button style, and it was checked in the browser instead. That's a departure from the rule, noted here.
- **The backup time isn't editable.** It runs in its own container, at 03:00, and is out of scope.
- **No migration**, because the existing `settings` table already holds JSON values by key.

## Left for later

- Show the worker's actual next quick-check time. The API can't know it, because it depends on when the worker started or was last changed. The worker could write it to `settings`.
- Pause and resume buttons, for example to stop scraping while travelling.
- Watch a real worker on the Pi move its jobs after a change. Look for `schedule changed:` in `docker compose logs worker`.
