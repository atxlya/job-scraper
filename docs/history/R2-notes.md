# R2a build notes: the dashboard

What was built, what was checked, and where the build differed from the [plan](plans/2026-11-11-r2-dashboard.md). Branch `r2-dashboard`, 2026-11-11. The 17 new companies (R2b) are a separate plan.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 295 passing |
| Web tests (`cd web && npm run check`) | 39 passing; type-check clean |
| Independent review of the whole branch | "With fixes": four fixed (below), the rest listed under "Left for later" |
| Real data, on a copy of `data/jobs.db` | Login, filters, search, job detail, Like/unlike, on-demand description (Accenture, fetched live), "Add company" detection, sources page, Mark all as seen (1,356 marked), phone and laptop widths, light and dark |
| Speed on 1,359 jobs | Every API call under 25 ms |
| Docker image | Builds with the dashboard inside (628 MB, was 555 MB) |
| **Not yet checked** | `docker compose` itself (Compose isn't installed on this Mac); the dashboard on the Pi over Tailscale; "Add company" saving a real new company (only detection was tried, to keep the real data clean); the "all jobs" filter list on a full Accenture-sized sweep (about 40,000 jobs) |

## What you need to do

1. Run `uv run python -m app.cli set-password` and paste the line it prints into `.env`.
2. Optionally, set `DASHBOARD_URL` in `.env` to where you'll open the dashboard. Telegram alerts then link to the job.
3. Start it, either with `docker compose up -d --build` or with:
   ```bash
   uv run uvicorn app.api.main:create_app --factory --port 8000
   ```

## Decisions made during the build

Each line gives the change from the plan, why, and what it costs if wrong. The plan's own decisions (D1–D14) are in the plan.

**Server**
- **The API starts as `app.api.main:create_app --factory`, not `app.api.main:app`.** Importing the module no longer opens the real database. *Cost:* the old command no longer works; compose and the runbook use the new one.
- **`set-password` prints the hash in single quotes.** Argon2 hashes contain `$`, which `.env` loaders can treat as variables.
- **Gemini "warn" without a quote counts as "Not checked".** This keeps R1's rule that unquoted warnings aren't trusted.
- **"Checking eligibility" only shows for possible tech internships.** Found in the real-data check: an Accenture "Payments Associate" said "updates automatically", but Gemini never reads such jobs. The job page now says "Eligibility is only checked for tech internships."
- **Fetching a missing description gives a clear error when none of the job's sources is turned on.** That message replaces a crash.
- **One field-update rule** (`_update_fields`) is shared by scraping and the on-demand fetch.
- **Eightfold company domain** = the host's last two parts (`apply.careers.microsoft.com` → `microsoft.com`). *Cost:* a `.co.uk`-style domain guesses wrong; the test fetch then fails and nothing is saved.

**Dashboard**
- **Newer library versions than planned:** React Router 8, TypeScript 7, Vite 8, Vitest 5. They were the current stable releases, and the APIs used didn't change.
- **Job cards are links** at every width: `?job=ID` on a laptop, `/jobs/ID` on a phone.
- **On a phone, filters open inline** under a "Filters (n)" button rather than in a pop-up sheet.
- **Switching Tech / All clears the company ticks**, since the counts differ per view.
- **"Add company" doesn't guess a name from an Oracle URL**, because hosts like `egug.fa.us2.oraclecloud.com` don't contain the company name. Workday and Eightfold URLs still pre-fill it.
- **The sources page hides old errors on healthy sources.** The worker keeps the last error after a later success; JPMorgan showed its robots.txt timeout next to "OK".
- **The theme is one shared setting**, applied on every page, so the login page follows your system theme too.

## Fixed after the review
- **A down site said "robots.txt doesn't allow fetching".** An unreachable robots.txt now raises its own error, and the job page says "Couldn't reach {site}".
- **An unexpected page from a site could crash the description fetch.** It now shows "Couldn't read the page" instead.
- **A note typed in the last 0.8 seconds before switching jobs was lost.** It's now saved when you leave.
- **"Mark all as seen" could mark jobs that arrived while you were reading.** The worker stamps a job's time before it saves, so a time cut-off can miss new jobs. It now marks up to the newest job number the list had when it loaded.

## Left for later (minor)

> **2026-11-11:** the code items below were fixed or found already fixed on branch `fix-deferred`; see [deferred-fixes-notes.md](deferred-fixes-notes.md). What's still open is listed there.
- The API docs (`/docs`, `/openapi.json`) open without login. They show the API's shape, not your data. Every `/api` route is locked, router by router, rather than locked by default.
- Logging out ends the session only in that browser. Changing the password doesn't sign out other devices.
- "Add company": pressing save twice at once gives an error on the second, and the same careers site added under two names is scraped twice.
- `docker compose up` rebuilds the search index every time. That's quick now, slower at about 40,000 jobs.
- Links inside descriptions open in the same tab, and relative links point at the dashboard.
- Fetching a description from a slow site can take a minute or two before it gives up.
- `/api/filters` counts companies and countries in Python. That's fine at 1,359 jobs (16 ms), but it should be re-measured after the first full Accenture sweep.
- The browser preview tool couldn't use this repo's launch config (it looks in a different folder), so checks ran against a server started by hand.
