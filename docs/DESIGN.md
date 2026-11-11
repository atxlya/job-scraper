# Job Scraper — Design

Agreed on 2026-11-10. This is the source of truth for what we are building. Per-company findings are in [companies.md](companies.md).

## 1. What it does

A service running 24/7 on a Raspberry Pi 5. It reads the official careers sites of 62 companies, stores every job it finds, and sends a Telegram alert for each new **tech internship**, including an eligibility check for a student based in **India**. A dashboard, reachable from anywhere through Tailscale, is used to browse jobs, tag them (Liked / Applied / Dismissed) and see whether each scraper is healthy.

The user is a B.Tech CSE student looking for internships. Graduation year does not matter.

## 2. Out of scope (decided)

- Match scores or comparing jobs against a profile. Jobs are listed, not ranked by fit.
- Any use of a resume (no parsing, no tailored drafts, no cover letters).
- Submitting applications automatically, or logging into any company account.
- Getting around bot protection (Cloudflare/Akamai challenges, WAFs) or ignoring robots.txt.
- Email and Discord alerts (the alert channel is pluggable, so they can be added later).
- A full analytics page.
- The 16 unsupported companies listed in [companies.md](companies.md#not-supported).

## 3. Scraping

### Sources and adapters
- Each company has one or more **sources**. A company that posts internships on a separate site has two (e.g. Visa `Visa` + `Visa_Early_Careers`).
- Each source uses an **adapter**: either a platform adapter shared across companies (Workday, Eightfold, Oracle HCM, Lever, Greenhouse, SuccessFactors-sitemap, RSS, notice-page) or a company-specific one (Google, Barclays, Amazon, …).
- Adding a company that uses a known platform is a config change only. The dashboard's "Add company" form detects the platform from a careers URL, runs a test fetch, and saves the source only if that test succeeds.
- Every adapter returns the same normalised `RawJob` shape. Nothing downstream knows which site a job came from.

### Schedule
| Run | When | What |
|---|---|---|
| Incremental | every 30 min, all sources (headless sources included, one at a time) | newest-first, filtered searches; fetch details only for job IDs not seen before |
| Full sweep | nightly, off-peak (≈02:00 IST) | crawl every page of every source; detect closed jobs and changed descriptions |
| Tracked re-check | daily | re-fetch detail pages of Liked/Applied jobs; this is how Google detects closed jobs |

### Politeness and compliance
- robots.txt is fetched, cached for 24 h, and **checked before every request**. A disallowed URL is never fetched.
- Rate limit per host: about 1 request every 2–3 s. Requests time out, retry with exponential backoff and jitter, and back off for longer on 429 or 5xx responses.
- An honest User-Agent that names no personal details.
- Google: only **page 1** of narrow searches (intern level × country, sorted by date), because robots.txt disallows `&page=`.
- No headless browser where plain HTTP works. Playwright is used only for the 7 sites in group D.

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
| `job_user_state` | job, `seen_at` (empty means new), tag (`liked` / `applied` / `dismissed` / none), note |
| `tag_history` | job, from → to, timestamp, optional date + note |
| `alerts` | job (unique, so never alerted twice), Telegram message ID, sent_at, edited_at |
| `scrape_runs` | source, kind (incremental / full / tracked), start, end, status, jobs read, site-reported total, new / updated / closed counts, error |
| `llm_usage` | per-day request and token counts, used for pacing |
| `settings` | tech keyword list, alert switches, model name, pacing limits |

**Deduplication:** unique on (`company`, `external_id`). If a source has no stable ID, fall back to the canonical URL, then to title + location.

**Changes:** a change in `content_hash` updates the row and adds a `job_changes` entry.

**Closed jobs:** never deleted. A job tagged Applied is never hidden.

## 5. Classification and Gemini

1. **Rules come first.** Keywords in the title and description set `is_internship` (intern, internship, trainee, apprentice, co-op, summer analyst, …, plus platform facets such as Workday `workerSubType`) and `is_tech` (software, data, ML/AI, security, cloud/DevOps, embedded, QA, IT, research). The keyword lists can be edited in settings.
2. **Gemini handles the rest**, for tech internships and for jobs the rules can't classify:
   - splits the posting into About / Responsibilities / Requirements / Preferred / Eligibility;
   - checks eligibility for someone in India: `ok`, or `warn` with the **exact quoted line** (e.g. US enrolment, local work authorisation);
   - classifies the unclear cases (titles batched about 20 per request).
3. **Guardrails:** the prompt requires verbatim quotes as evidence, and the output is validated against a JSON schema. A quote that does not appear in the source text is rejected, and the result falls back to `unknown`. Gemini never invents a requirement.
4. **Model:** `gemini-3.5-flash-lite`, free tier only, with no paid fallback. The model name is a setting.
5. **Pacing:** stay well under the limits: at most about 5 requests per minute, plus a daily cap of 50–70% of the limit actually observed, tuned from 429 responses. Google publishes no fixed free-tier table; limits are per project and reset at midnight Pacific time (13:30 IST).
6. **Queue priority:** new jobs first, then the backlog (newest first, India first). The first run's backlog of about 1,000–1,500 internships is spread over 2–3 days.
7. **Gemini down or out of quota:** the job is still stored and still alerted, marked "eligibility not checked yet", and analysed later.

Free-tier inputs may be used by Google to improve its products. This is acceptable because only public job text is sent.

## 6. Alerts (Telegram)

- **Trigger:** a newly discovered job with `is_internship ∧ is_tech`. All locations count.
- **Message:** 🏢 company · title · 📍 location · 🗓 posted date · apply link · dashboard link · `🔍 checking eligibility…`. Once the analysis finishes, **the same message is edited** to show ✅ or ⚠️ with the quoted line.
- **First run per source:** stores everything quietly and sends one summary ("Loaded N existing internships").
- **Bursts:** more than 10 new internships in one run are sent as one grouped message.
- **No repeats:** each job gets at most one alert, even if it closes and reopens (the `alerts` table has a unique key on the job).
- **Government notices:** an alert is sent only when the notice title looks internship-like (intern / trainee / apprentice / JRF / project / summer / fellowship), with Gemini deciding unclear cases. The PDF link is included.
- **Partial sources** (Cognizant, SAP): an alert is sent when the title looks like a tech internship, marked "details unavailable — open link".
- **Scraper health:** a warning is sent when a source fails 3 runs in a row or its job count drops by more than 50%. At most one warning per source per day, plus a "recovered" message.

## 7. Dashboard

- **Default view:** tech internships, newest first, with "new" badges. A toggle switches to all jobs.
- **Filters:** company, location/country, eligibility (✅ / ⚠️ / unknown), posted date, tag, full-text search (SQLite FTS5), "show dismissed".
- **Job page:** sections, eligibility result with quote, original and apply links, change log, buttons for Like / Applied / Dismiss / remove tag, and a note.
- **Bulk action:** "Mark all as seen".
- **Stats strip:** new today · open tech internships · liked · applied.
- **Health panel:** one row per source: last success, job count, last error, failure streak.
- **"Add company" form:** see §3.
- **Look:** chosen from 2–3 mockups before any UI code is written. Light and dark themes; works on phone and laptop.
- **Access:** single-user password login (argon2 hash, HTTP-only session cookie), reachable over Tailscale. Nothing is exposed to the public internet.
- **Built in R2:** the decisions made while building it (D1–D14: where added companies are stored, default filters, closed and dismissed jobs, and so on) are in the [R2 dashboard plan](superpowers/plans/2026-11-11-r2-dashboard.md#decisions-this-plan-makes-the-spec-is-silent-or-open), and the results are in [R2-notes.md](R2-notes.md).

## 8. Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| HTTP | httpx (with HTTP/2), selectolax/BeautifulSoup for HTML, `extruct`-style JSON-LD parsing |
| Headless | Playwright Chromium (group D only) |
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
| **R4** | Headless (Playwright) sites | 62 |

Each release is checked against the live sites before the next one starts. Development and testing happen on the Mac, then the same Compose stack is deployed to the Pi.
