# Stages after Applied

Branch `application-stages`, 2026-11-12, cut from `telegram-buttons` (you chose this, because it builds on that branch's shared `set_tag()` and Telegram buttons). Merge `telegram-buttons` first. This is prompt 6 in [next-prompts.md](next-prompts.md). The stage model and the mockups were agreed before any code was written.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 726 passing (was 703) |
| Web tests (`cd web && npm run check`) | 136 passing (was 120); type-check clean; build OK |
| Lint (`ruff check`, `ruff format --check`) | Clean |
| Migration 0006 on a copy of the real database | A test copies `data/jobs.db` with SQLite's backup, upgrades it, and checks that every `job_user_state` and `tag_history` row is unchanged and no stage is set; then it downgrades and checks again. It skips on a machine without `data/jobs.db` |
| On a copy of the real database, in the browser | Took 4 liked jobs through stages with the real API (a stage on a job that is only liked was refused, 409). Checked the job page and "Your applications" at 1440 px and 375 px, light and dark; the stage form; `l` on a job at Offer (refused, with the message); no server errors |
| **Not checked** | A real phone (only browser emulation); Safari; the Telegram "change it on the dashboard" answer against the real bot (fake Telegram only, as in [telegram-buttons-notes.md](telegram-buttons-notes.md)); a real `window.confirm` on a phone browser |

## What changed

**Data** (migration `0006`)
- `job_user_state.stage`: `oa` / `interview` / `offer` / `rejected`, or empty for "just applied". It only means something while the tag is `applied`.
- `tag_history.from_stage` / `to_stage`. A stage step is a row whose tag goes from `applied` to `applied`. A tag change away from Applied records the stage it had in `from_stage`.

**Rules** (`app/core/tags.py`)
- `set_stage()` refuses a job that isn't Applied (the API answers 409 "Mark it Applied first.").
- `set_tag()` clears the stage when the tag leaves Applied. Setting Applied on a job that already has it keeps the stage.
- `application_steps()` returns the current application's steps: from the last move into Applied, then each stage step. A step's date is the one you gave, or the day it was recorded (IST).

**API**
- `PUT /api/jobs/{id}/stage` `{stage, event_date, note}`. Sending `stage: null` goes back to just Applied.
- `GET /api/applications`: every applied job, closed ones included, newest step first. It uses two queries, not one per job.
- Job cards and details carry `stage`; details also carry `steps`.
- The stats "last on" date for Applied now ignores stage steps. Otherwise moving a job to Interview would have changed "last applied on".

**Dashboard**
- Job page: the "Your application" box (stage picker, date-and-note form, timeline), as in the mockup. On a phone the "›" separators are hidden, and a step's note sits under the stage instead of being cut short.
- `/applications`: as in the mockup. The laptop link is in the header; on a phone it's in the ⋯ menu as "Your applications".
- A card's badge shows the stage ("Interview") instead of "Applied".

**Guards for a job that has a stage** (you chose: confirm on the page, block the quick ones)
- Job page: removing Applied, Like and Dismiss ask first.
- Keys `l` `a` `d` `u` and both swipes do nothing, and the toast says "At Interview: change it on the job page".
- Telegram: every button answers "At Interview: change it on the dashboard" and changes nothing.

## Bug found while building

**Two siblings had the same React key.** The stage box and the note box both used `key={job.id}`. After a stage was saved, the old box stayed on screen beside the new one. A test caught it; the stage box now has its own key.

## Decisions

- **A separate stage field, not more tag values** (you chose this). *Cost if wrong:* one more column to keep in step; `set_tag` and `set_stage` are the only writers.
- **Rejected can be picked from any stage, and a stage can go back** (Interview → OA). Each change is its own step. *Cost:* a mistaken click adds a step to the timeline; the change log shows it.
- **The timeline starts at the last move into Applied.** If you remove Applied and apply again, the old steps stay in the change log but not in the timeline or "Your applications".
- **Laptop columns are Applied, OA and Interview, plus "since last step"**, as in the mockup. Offer and Rejected show in that last column ("Offer 10 Nov · 2 days").
- **The Applied stat still opens the list filtered to applied jobs**, not "Your applications". The prompt only asked about its count.

## Left for later

- **No filter by stage in the job list.** Use "Your applications".
- **Telegram buttons don't show the stage.** A job at Interview still shows "✓ Applied".
- **Applied jobs that have no history row** (if any were tagged before history existed) show no steps, and "since" counts from when the job was first seen. The real database has no applied jobs yet, so none.
