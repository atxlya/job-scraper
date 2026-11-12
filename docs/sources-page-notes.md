# Sources page

Branch `sources-page`, 2026-11-12. This is prompt 3 in [next-prompts.md](next-prompts.md). The mockup was approved before any UI code was written.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 666 passing (was 658) |
| Web tests (`cd web && npm run check`) | 101 passing (was 88); type-check clean; build OK |
| Lint (`ruff check`, `ruff format --check`) | Clean |
| Migration 0004 on a copy of the real database | Upgrades cleanly; a test also checks upgrade and downgrade |
| Query time (see below) | `/api/sources` 1.6 ms on the real copy, **3.9 ms with a year of runs** |
| Page on a demo copy | Laptop 1440 light and dark, phone 375 light: no sideways scrolling; hover tooltip, row opening and phone cards all work |
| **Not checked** | The page with real history. The real database has only 37 runs, all incremental, from one evening, so every chart there says "No full sweep yet". The screenshots used a demo copy with **made-up** runs: 14 nights for every source, one source failing 4 nights, one dropping by half, one partial run. Also not checked on a real phone |

## What changed

**Order and status.** Statuses are now **failing** (failed runs in a row), **partial** (the last run was partial), **count dropped** (the existing job-count-drop warning is active), **OK**, and **not run yet**. The order is:
1. failing, longest streak first;
2. partial and count dropped;
3. OK, by company;
4. not run yet;
5. turned-off sources last, whatever their state.

The server sorts; the page keeps its order.

**Summary line.** For example: "62 OK · 1 partial · 1 count dropped · 1 failing · Next full sweep 02:00 IST (in 4 h 11 min)". Turned-off sources are counted as "off". The time comes from a new `GET /api/schedule`. The worker and the API now read the run times from one place, `app/core/schedule.py`, so the page can't drift from the real schedule.

**14-night chart** (you chose this over plotting every run):
- One point per IST night: the jobs read by that night's **full** sweep. Incremental runs only read the newest jobs (Accenture 54 of 2,000), so mixing them in would make the line jump every 30 minutes.
- If a night has more than one full run, the latest one counts.
- The line sits on a zero baseline, so a drop by half looks like one. Small changes stay flat.
- A failed night is an orange dot and breaks the line; a night with no sweep is a gap.
- Hover shows "11 Nov · 27 jobs". Screen readers get the whole series as the chart's label.
- Drawn as inline SVG; no chart library.
- The new orange (`--bad`: light `#c2410c`, dark `#fb923c`) passes the dataviz validator's contrast check on both surfaces. Its "lightness band" check flags the dark orange, but that check is for multi-color palettes, not a single status color. The failing state is also shown by the "⚠ Failing" pill, so it never relies on color alone.

**Last run.** Its kind, duration and age, e.g. "incremental · 40 s · 18m ago".

**Run history.**
- Clicking a row (a real button, so it works from the keyboard too) opens that source's last 20 runs underneath.
- Each run shows: kind, start (IST), duration, status, read / site total, new, updated, closed, and the error.
- New endpoint: `GET /api/sources/{key}/runs`.

**Phone.** One card per source: name, status, job count, last run, chart and the error if failing. Tap a card for its runs.

## Query time and indexes

`scrape_runs` gets about 65 × 50 = 3,250 rows a day, about 1.2 million a year. Timings are the median of 7 runs on this Mac, using the real code against copies of the database:

| Database | `/api/sources` | A source's runs |
|---|---|---|
| Real copy (37 runs), before | 1.6 ms | 0.2 ms |
| Real copy plus a year of made-up runs (1,186,287), before | 93.2 ms | 22.6 ms |
| Same, with the two new indexes | 47.6 ms | 0.3 ms |
| Same, with indexes and the last run looked up per source | **3.9 ms** | **0.4 ms** |
| Same query without the new indexes | 1,205.7 ms | 24.4 ms |

Migration `0004` adds:
- `ix_scrape_runs_source_started (source_id, started_at)`: each source's newest runs, both for the run history and for "last run" (one index lookup per source instead of scanning every run).
- `ix_scrape_runs_kind_started (kind, started_at)`: the last 14 nights of full runs across all sources.

`docker compose up` already runs `alembic upgrade head`, so the indexes are added on the next deploy. On the Pi this takes a few seconds on a small table.

## Decisions

- **Nightly full sweeps, not every run, on the chart** (you chose this). *Cost:* the chart says nothing about the 30-minute runs; a failing incremental shows in the status and the last run, not on the chart.
- **"Partial" comes from the last run of any kind**, the daily tracked re-check included. *Cost:* a tracked re-check with one failed job page marks the source partial until its next good run.
- **A new `/api/schedule` instead of putting the time in `/api/sources`.** The Scraper health panel on the dashboard also reads `/api/sources` as a list, and that stays as it was.

## Left for later

- **Run history covers only about 10 hours.** Twenty runs at one every 30 minutes means the nightly full run drops out by mid-afternoon. Options: always pin the latest full run on top, or add "show more".
- **The dashboard's Scraper health panel counts only "OK" as healthy.** Partial and count-dropped sources now count as neither healthy nor failing there.
- **Some sources have no job count** ("—", e.g. Myntra in this database): `last_job_count` is empty until a run sets it. That's the data, not this page.
- **No pruning of `scrape_runs`.** With the indexes a year of runs is fast, but the table (about 100 MB a year) grows forever. A monthly cleanup keeping 90 days would cap it.
