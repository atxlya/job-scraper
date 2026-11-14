# Job Scraper — Design

Agreed on 2026-11-10. This is the source of truth for what we are building. Per-company findings are in [companies.md](companies.md).

## 1. What it does

A service running 24/7 on a Raspberry Pi 5. It reads the official careers sites of 106 companies, stores every job it finds, and sends a Telegram alert for each new **tech internship**, including an eligibility check for a student based in **India**. A dashboard, reachable from anywhere through Tailscale, is used to browse jobs, tag them (Liked / Applied / Dismissed) and see whether each scraper is healthy.

The user is a B.Tech CSE student looking for internships. Graduation year does not matter.

## 2. Out of scope (decided)

- Match scores or comparing jobs against a profile. Jobs are listed, not ranked by fit.
- Any use of a resume (no parsing, no tailored drafts, no cover letters).
- Submitting applications automatically, or logging into any company account.
- Getting around bot protection (Cloudflare/Akamai challenges, WAFs) or ignoring robots.txt.
- Email and Discord alerts (the alert channel is pluggable, so they can be added later).
- A full analytics page.
- The 17 unsupported companies listed in [companies.md](companies.md#not-supported).

## 3. Scraping

### Sources and adapters
- Each company has one or more **sources**. A company that posts internships on a separate site has two (e.g. Visa `Visa` + `Visa_Early_Careers`).
- Each source uses an **adapter**: either a platform adapter shared across companies (Workday, Eightfold, Oracle HCM, Lever, Greenhouse, SuccessFactors-sitemap, RSS, notice-page, RippleHire, Spire2Grow, MyNextHire) or a company-specific one (Google, Barclays, Amazon, …).
- Adding a company that uses a known platform is a config change only. The dashboard's "Add company" form detects the platform from a careers URL, runs a test fetch, and saves the source only if that test succeeds.
- Every adapter returns the same normalised `RawJob` shape. Nothing downstream knows which site a job came from.

### Schedule
| Run | When | What |
|---|---|---|
| Incremental | every 30 min by default, all sources | newest-first, filtered searches; fetch details only for job IDs not seen before |
| Full sweep | nightly, off-peak (02:00 IST by default) | crawl every page of every source; detect closed jobs and changed descriptions |
| Tracked re-check | daily (04:00 IST by default) | re-fetch detail pages of Liked/Applied jobs; this is how Google detects closed jobs |

The three can be changed on the dashboard's Sources page (**Schedule › Edit**):
- **Storage:** the values are saved in the `settings` table under the key `schedule`. With no row, or a row that can't be used, the defaults above apply.
- **Pick-up:** the worker re-reads them every 60 s and moves its jobs with `reschedule_job`, so a change takes effect within a minute, with no restart. Changing the quick-check interval restarts its count from that moment.
- **Limits:**
  - the quick check is 15–360 minutes apart, so that 100+ sites are never hit harder than every 15 minutes;
  - the full sweep and the re-check start at least an hour apart.
  - The API answers 422 with the reason, and the page shows it.

### Politeness and compliance
- robots.txt is fetched, cached for 24 h, and **checked before every request**. A disallowed URL is never fetched.
- Rate limit per host: about 1 request every 2–3 s. Requests time out, retry with exponential backoff and jitter, and back off for longer on 429 or 5xx responses.
- An honest User-Agent that names no personal details.
- Google: only **page 1** of narrow searches (intern level × country, sorted by date), because robots.txt disallows `&page=`.
- No headless browser where plain HTTP works. None of the 7 sites planned as headless (group D) needed a browser: 6 work over plain HTTP and 1 is blocked by robots.txt (see [R4-notes.md](history/R4-notes.md)).

### Accuracy checks
- Each run compares the number of jobs it read with the total the site reports. A mismatch marks the run **failed**, not successful.
- Accenture's Workday caps `total` at 2000, so queries are split by facet until each slice is under that cap.
- A job is marked **closed** only if (a) its detail page returns a "not found" response, or (b) it is missing from **2 consecutive complete** full sweeps. A single bad run therefore can't close jobs.

## 4. Data model (SQLite, WAL mode, SQLAlchemy + Alembic)

| Table | Purpose |
|---|---|
| `companies` | name, slug, `supported` flag, unsupported reason |
| `sources` | company, adapter type, adapter config (JSON), enabled, last success, last error, consecutive failures, last job count |
| `jobs` | company, source, `external_id`, canonical URL, apply URL, title, locations, country codes, remote type, employment type, posted date, description (cleaned HTML), `content_hash`, `is_internship`, `is_tech`, `state` (open/closed), `first_seen_at`, `last_seen_at`, `closed_at` |
| `job_changes` | job, changed_at, which fields changed (no full copy of old versions) |
| `job_analysis` | job, model, prompt version, sections (About / Responsibilities / Requirements / Preferred / Eligibility), eligibility (`ok` / `warn` / `unknown`), quoted eligibility line |
| `job_user_state` | job, `seen_at` (empty means new), tag (`liked` / `applied` / `dismissed` / none), stage (`oa` / `interview` / `offer` / `rejected`, only while the tag is `applied`; empty means just applied), note |
| `tag_history` | job, from → to tag, from → to stage, timestamp, optional date + note. A stage step is a row whose tag goes from `applied` to `applied` |
| `alerts` | job (unique, so never alerted twice), Telegram message ID, sent_at, edited_at |
| `closed_alerts` | job (unique, so a "closed" message is sent at most once), Telegram message ID, sent_at |
| `scrape_runs` | source, kind (incremental / full / tracked), start, end, status, jobs read, site-reported total, new / updated / closed counts, error |
| `llm_usage` | per-day request and token counts, used for pacing |
| `settings` | tech keyword list, alert switches, model name, pacing limits, the Telegram `getUpdates` offset |

**Deduplication:** unique on (`company`, `external_id`). If a source has no stable ID, fall back to the canonical URL, then to title + location.

**Changes:** a change in `content_hash` updates the row and adds a `job_changes` entry.

**Closed jobs:** never deleted. A job tagged Applied is never hidden, whatever its stage (Rejected included) and whether or not it has closed.

**Stages after Applied:** a separate field next to the tag, not more tag values, so every rule about applied jobs (never hidden, the Applied count, the daily re-check, "closed" messages) holds at every stage. Leaving Applied clears the stage; its history stays. See [stages-notes.md](history/stages-notes.md).

## 5. Classification and Gemini

1. **Rules come first.** Keywords in the title and description set `is_internship` (intern, internship, trainee, apprentice, co-op, summer analyst, …, plus platform facets such as Workday `workerSubType`) and `is_tech` (software, data, ML/AI, security, cloud/DevOps, embedded, QA, IT, research). The keyword lists can be edited in settings.
2. **Gemini handles the rest**, for tech internships and for jobs the rules can't classify:
   - splits the posting into About / Responsibilities / Requirements / Preferred / Eligibility;
   - checks eligibility for someone in India: `ok`, or `warn` with the **exact quoted line** (e.g. US enrolment, local work authorisation);
   - classifies the unclear cases first, from the title alone, 20 titles per request, so jobs that turn out not to be tech internships leave the queue without a full read.
3. **Guardrails:** the prompt requires verbatim quotes as evidence, and the output is validated against a JSON schema. A quote that does not appear in the source text is rejected, and the result falls back to `unknown`. Gemini never invents a requirement.
4. **Model:** `gemini-3.5-flash-lite`, free tier only, with no paid fallback. The model name is a setting.
5. **Pacing:** Google's free tier for this model allows 15 requests a minute and 500 a day (seen in AI Studio, Nov 2026). The defaults use all of it, to clear the backlog: `GEMINI_RPM=15`, `GEMINI_DAILY_CAP=500`. Any other use of the same key (AI Studio, `analyze-one`) counts against the same 500, so the last few requests of a day may get a 429. Each minute spends one request on unclear titles (when there are any) and the rest on full reads. A 429 pauses 2 minutes; a second one that day stops for the day and learns a lower cap. A 503 ("high demand") is Google being busy, not our quota: it pauses 2 minutes and the job stays queued. Limits are per project and reset at midnight Pacific time (13:30 IST).
6. **Queue priority:** new jobs first, then the backlog (newest first, India first). The first run's backlog of about 1,000–1,500 internships is spread over 2–3 days.
7. **Gemini down or out of quota:** the job is still stored and still alerted, marked "eligibility not checked yet", and analysed later. A job whose read failed for another reason is marked `failed`; `python -m app.cli retry-failed` puts those back in the queue.

Free-tier inputs may be used by Google to improve its products. This is acceptable because only public job text is sent.

## 6. Alerts (Telegram)

- **Trigger:** a newly discovered job with `is_internship ∧ is_tech`. All locations count.
- **Message:** 🏢 company · title · 📍 location · 🗓 posted date · apply link · dashboard link · `🔍 checking eligibility…`. Once the analysis finishes, **the same message is edited** to show ✅ or ⚠️ with the quoted line.
- **Tag buttons:** each alert sent on its own has ❤️ Like · ✅ Applied · 🗑 Dismiss under it. A press sets the tag exactly as the dashboard does (the same function writes the `tag_history` row; Applied is dated today, IST), Telegram shows "Liked" / "Applied" / "Dismissed" / "Tag removed", and the buttons are redrawn: the current tag shows as "✓ Liked", and pressing it again removes it. Every edit of an alert redraws the whole message from the database, so the eligibility line and the buttons are both kept, whichever edit comes last.
  - **How presses arrive:** the worker long-polls `getUpdates` (no webhook, because the Pi is only on Tailscale). The next offset is stored in `settings`, in the same commit as the tag change, so nothing is handled twice after a restart.
  - **Who can press:** only presses in the chat `TELEGRAM_CHAT_ID` names count. Others get no answer.
  - **A job with a stage after Applied** isn't changed by any button: Telegram answers "At Interview: change it on the dashboard".
  - **No buttons** on grouped burst messages, first-run summaries, health warnings or "closed" messages. Alerts sent before this was added have none either, until the eligibility edit adds them.
  - A tag changed on the dashboard shows on the buttons only at that alert's next edit. A button's press always sets what its label says, so an out-of-date button can't undo a dashboard change.
- **Closed jobs:** when a job you liked or applied to closes (either rule in §3), you get "🔒 Closed: company · title" with the dashboard link. Several in one round go in one grouped message. At most one per job, ever (`closed_alerts` is unique on the job). A job tagged only after it had closed doesn't count. See [telegram-buttons-notes.md](history/telegram-buttons-notes.md).
- **First run per source:** stores everything quietly and sends one summary ("Loaded N existing internships").
- **Bursts:** more than 10 new internships in one run are sent as one grouped message.
- **No repeats:** each job gets at most one alert, even if it closes and reopens (the `alerts` table has a unique key on the job).
- **Government notices:** an alert is sent only when the notice title looks internship-like (intern / trainee / apprentice / JRF / project / summer / fellowship), with Gemini deciding unclear cases. The PDF link is included.
- **Partial sources** (Cognizant, SAP): an alert is sent when the title looks like a tech internship, marked "details unavailable — open link".
- **Scraper health:** a warning is sent when a source fails 3 runs in a row or its job count drops by more than 50%. At most one warning per source per day, plus a "recovered" message.

## 7. Dashboard

- **Default view:** tech internships, newest first, with "new" badges. A toggle switches to all jobs.
- **Job cards:** company icon (a logo file from `web/src/logos/`, else initials on the company's own color), title (2 lines at most), company · flag + "City, Country" · "+N" more locations · age, an India or Remote chip, and an eligibility badge only once there is a result (Eligible / Check needed). On a laptop the list and the details split 40/60, and the first job opens by itself; it isn't marked seen and its description isn't fetched until you pick it. See [job-list-notes.md](history/job-list-notes.md).
- **Filters:** company, location/country, eligibility (✅ / ⚠️ / unknown), posted date, tag, full-text search (SQLite FTS5), "show dismissed".
- **Job page:** sections, eligibility result with quote, original and apply links, change log, buttons for Like / Applied / Dismiss / remove tag, and a note.
  - **Once a job is Applied:** a "Your application" box with a stage picker (Applied › OA › Interview › Offer, and Rejected from any of them). Picking a stage asks for its date (today by default) and an optional note. Under it, a timeline of the steps since the last move into Applied, newest first, with each date and how long ago it was.
  - **A job with a stage asks before it loses it:** removing Applied, Like and Dismiss show a confirm. The triage keys and swipes leave it alone and say "At Interview: change it on the job page", and so do the Telegram buttons.
- **Your applications** (`/applications`; header link on a laptop, ⋯ menu on a phone): every applied job grouped by stage, most advanced first and Rejected last, closed ones included with a "Closed" chip. On a laptop, a table per stage with the dates of Applied, OA and Interview and the time since the last step. On a phone, a row of stage chips that jump to each group, and one card per job.
- **Bulk actions,** in the list's title row:
  - "Mark all as seen".
  - "Export CSV" (shown when the list isn't empty). It downloads `/api/jobs.csv` with the list's filters and order: company, title, locations, posted, tag, stage, eligibility, apply URL, dashboard URL, first seen (IST), then Gemini's about, responsibilities, requirements and preferred (empty until the job is read), and the full description as plain text, a line per paragraph or bullet. A long cell is cut at 32,000 characters, under the spreadsheet limit. The API sends it in batches of 500 rows: 40,000 jobs took 12 s on the Mac (19 MB, 46 MB peak memory); a liked or tech list takes under a second. A cell starting with `=` `+` `-` `@`, a tab or a carriage return gets a leading `'`, so a spreadsheet won't run it as a formula.
- **Home-screen app:** `web/public/manifest.webmanifest` (standalone, start `/`), icons made from the logo by `scripts/make_icons.py`, and an apple-touch-icon. The phone's status bar takes the header color of the theme in use. There's no service worker and no offline mode: every visit loads live data. The manifest and icons are served without login, because they hold no data.
- **Triage:** on a laptop, single keys act on the open job (j/k move, l Like, a Applied today, d Dismiss and move on, u remove tag, z undo, o open the apply link, / search, Esc, ? the list); on a phone, swipe a card right to Like or left to Dismiss. Dismissing and swiping show a 5-second Undo toast. See [triage-notes.md](history/triage-notes.md).
- **Stats strip:** new today · open tech internships · liked · applied (every applied job, whatever its stage; "last on" is the last move into Applied, not a stage step). Each one is a button that shows the jobs it counts (it replaces the other filters, so the list matches the number). Tiles on laptop and tablet, one sideways-scrolling row of chips on a phone.
- **Header:** phone: logo, search and one ⋯ menu (Add company, Sources, Theme, Log out, Log out everywhere). Laptop: search, Add company, theme and an Account menu. See [phone-header-notes.md](history/phone-header-notes.md).
- **Health panel:** one row per source: last success, job count, last error, failure streak.
- **Sources page:** a summary line ("62 OK · 1 partial · 1 failing") and the next full sweep; failing sources first (longest streak first), then partial runs and count-drop warnings, then OK by company. Each source has a 14-night chart of its full sweep's read count (a failed night is an orange dot), its last run's kind and duration, and its last 20 runs on a click. Cards on a phone. See [sources-page-notes.md](history/sources-page-notes.md).
- **"Add company" form:** see §3.
- **Look:** chosen from 2–3 mockups before any UI code is written. Light and dark themes; works on phone and laptop.
- **Access:** single-user password login (argon2 hash, HTTP-only session cookie), reachable over Tailscale. Nothing is exposed to the public internet.
- **Built in R2:** the decisions made while building it (D1–D14: where added companies are stored, default filters, closed and dismissed jobs, and so on) are in the [R2 dashboard plan](history/plans/2026-11-11-r2-dashboard.md#decisions-this-plan-makes-the-spec-is-silent-or-open), and the results are in [R2-notes.md](history/R2-notes.md).

## 8. Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| HTTP | httpx (with HTTP/2), selectolax/BeautifulSoup for HTML, `extruct`-style JSON-LD parsing |
| Headless | none (no site needs it; see [R4-notes.md](history/R4-notes.md)) |
| Scheduler | APScheduler in a separate **worker** process |
| LLM | provider interface, with a Gemini implementation (`google-genai`) |
| Alerts | channel interface, with a Telegram Bot API implementation |
| Frontend | React + Vite + TypeScript + Tailwind, built to static files and served by FastAPI |
| Deploy | Docker Compose (`api`, `worker`, `backup`), images built for arm64 and amd64, `restart: unless-stopped`, Docker enabled at boot |

## 9. Repo layout (planned)

```
app/
  core/        config (env), db, models, migrations
  http/        polite client: robots cache, per-host limiter, retries
  adapters/    base.py, workday.py, eightfold.py, oracle_hcm.py, lever.py,
               greenhouse.py, successfactors.py, rss.py, notice_page.py,
               company/google.py, company/barclays.py, ...
  pipeline/    normalise, upsert/dedupe, change + close detection, rules
  llm/         provider.py, gemini.py, pacer.py, prompts/
  notify/      channel.py, telegram.py
  worker/      scheduler + job definitions
  api/         FastAPI routes, auth
web/           React dashboard
config/        sources.yaml (company + source registry), keywords.yaml
tests/         fixtures/ (recorded real responses), adapter + pipeline tests
docs/
```

## 10. Reliability and operations

- Each source runs in isolation: one failing source never blocks the others.
- Writes are transactional: a run's results are committed together or not at all.
- `/healthz` endpoint for each container. Docker restarts crashed containers.
- Logs are structured JSON with rotation, and capped in size to protect the disk.
- **Backups:** a nightly `sqlite3 .backup` snapshot is kept on the Pi for 30 days, and a weekly copy is pushed to the Mac over Tailscale whenever it is online.
- Secrets (Telegram token, Gemini key, dashboard password hash) live in `.env` and are never committed.

## 11. Testing

- Every adapter has tests against **recorded real responses** in `tests/fixtures/`. No invented sample jobs.
- A `live-check` command hits each real source and asserts it gets more than 0 jobs, that the required fields are present, and that the count matches the site's reported total. It runs before every release and weekly on the Pi.
- Pipeline tests cover dedupe, change detection, closing after 2 missed sweeps, alert de-duplication and burst grouping.

## 12. Releases

| Release | Scope | Companies |
|---|---|---|
| **R1** | Whole pipeline (DB, rules, Gemini, Telegram, worker, Docker) on Google, NVIDIA, Barclays; Workday + Eightfold + Oracle HCM adapters | 28 |
| **R2** | Dashboard (after mockups); Lever, Greenhouse and the remaining company-specific JSON adapters | 43 |
| **R3** | SuccessFactors sitemaps, RSS, government/notice pages, partial sources | 55 |
| **R4** | Last 7 sites (planned as headless; all plain HTTP) | 61 |
| **Added 2026-11-13** | 45 more on Greenhouse and Workday: quant and trading firms, banks, chip makers, big tech ([candidate-companies.md](candidate-companies.md)) | 106 |

Each release is checked against the live sites before the next one starts. Development and testing happen on the Mac, then the same Compose stack is deployed to the Pi.
