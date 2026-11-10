# R1 build notes

What was built for R1, what was checked, and every place the build differed from the [plan](superpowers/plans/2026-11-10-r1-pipeline.md). Branch `r1-pipeline`, 2026-11-10.

## Status

| Check | Result |
|---|---|
| Tests (`uv run pytest`) | 172 passing |
| Live check, quick mode, all 32 sources (28 companies) | 32/32 return real jobs |
| First real run into a scratch database | 1,351 jobs stored, no duplicates, all 32 sources OK, 23 min |
| Second real run | 9 new jobs, nothing duplicated, 90 s |
| Docker image | Builds on ARM (the Pi's architecture), 555 MB; database setup and `/healthz` work inside it |
| **Not yet checked** | Gemini against a real job and 24 h with Telegram (both need your keys); `docker compose` itself (the Compose plugin is not installed on this Mac); full nightly sweep of the largest sources (Accenture alone is about 1.5 h) |

## Decisions made during the build

Each line gives what changed from the plan, why, and what it costs if the decision is wrong.

**Database and storage**
- Python 3.13 instead of 3.12, because it is what this Mac has. *Cost:* change one version pin.
- Added `Source.warning_active` and per-source miss counts (`Job.missed_by_source`). A job listed on two of a company's sites (e.g. Visa's two sites) closes only when **both** have missed it twice. *Cost:* two extra columns.
- An empty value in a listing never overwrites a stored one, because listing pages often lack descriptions.
- A "complete" sweep that returns 0 jobs from a source that has open jobs closes nothing; it is treated as a broken page.

**Scraping**
- **robots.txt:** replaced Python's built-in parser with one that follows the standard (RFC 9309, longest rule wins). The built-in one wrongly blocked NVIDIA's allowed job API. robots.txt returning 4xx or HTML means no rules; 5xx or unreachable (after 3 tries) means don't fetch for now.
- **Workday:** the job total is read from page 1, because later pages report 0. Postings with no title or link (seen at Accenture) are skipped. Accenture's 40,000 jobs are split by country, then job family, then worker type, to get past Workday's 2,000-result cap.
- **Oracle:** results are sorted newest first, so the 30-minute check sees new jobs.
- **Google:**
  - The nightly sweep counts as complete when every country search fits on page 1. Each currently has fewer than 20 jobs, so closed-job detection works for Google without breaking robots.txt.
  - The 30-minute check runs only India plus a newest-anywhere search, because each page is 1.2 MB.
  - *Cost:* an internship outside India is found up to 24 h late if the newest-anywhere search misses it.
- **Eightfold** (Microsoft, Qualcomm, Morgan Stanley, PayPal, HSBC): none has an internship filter, so their 30-minute check searches for "intern". The nightly sweep still reads everything.
- **Detail pages are fetched only for possible tech internships.** Otherwise the first nightly sweep would fetch about 40,000 pages for Accenture alone (about 28 h). Other jobs are stored from the listing, without a description. *Cost:* the dashboard's "all jobs" view needs to fetch those descriptions on demand (R2).

**Classification and Gemini**
- Added a "maybe internship" word list (graduate, programme, early careers…) whose matches go to Gemini instead of being guessed.
- "IT" counts as tech only in capitals.
- A title with both tech and non-tech words is marked unclear and goes to Gemini. Examples: "Sales Operations & Data", "Materials Engineering".
- **Rate limits:** the plan's rule would have stopped all Gemini calls for the day after a single rate-limit response. Now:
  - the first rate-limit response pauses 2 minutes;
  - a second one on the same day stops for that day and sets a lower daily cap (60% of that day's usage) for later days.
- Known non-tech or non-internship jobs never cost a Gemini call.
- An eligibility warning that comes without a quote becomes "unclear".
- **Degree level** (added 2026-11-11, prompt version 2): a role only for PhD, Master's or MBA students gets a warning, since you are a Bachelor's student. It is caught two ways:
  - by the title (e.g. "PhD Intern"), with no Gemini call needed. On the test-run data this flagged 29 of 239 tech internships, all correctly;
  - by Gemini reading the posting, which quotes the line (e.g. "Pursuing a PhD program…").
  - A title or line that also accepts Bachelor's students ("BS/MS") is not flagged. The alert is still sent, so nothing is hidden. *Cost:* a role whose degree rule appears only in an unusual wording may slip through as "Eligible".

**Alerts and health**
- **No skipped or double alerts:** each job gets one alert record once handled. A source's first load records its jobs silently. Jobs without a record are retried every run, which covers Telegram outages and jobs Gemini classifies later.
- **Health checks** run once per round of sources. If 80% or more of the sources fail, you get one "network down?" message (at most every 6 h) instead of 28 warnings.
- **Count-drop warnings** compare nightly sweeps only.

**Running on one machine**
- A database write is never left open while waiting on the network; otherwise parallel sources would hit "database is locked". A test covers this.
- A per-source lock stops the nightly and 30-minute runs from scraping the same site at once.
- Any error in one source, or in the alert step, is logged and never stops the other sources.

**Deployment**
- Backups use SQLite's backup function from Python, because the slim image has no `sqlite3` tool.
- The weekly copy to the Mac runs from the Pi's crontab, since it needs the Pi's SSH key.
- A one-shot `migrate` service prepares the database before the other services start.

## Left for later (minor)
- Jobs stored from listings only (not possible internships) have no posted date or description until R2 fetches them on demand.
- The Docker image is 555 MB; a slimmer build is possible.
- `google-genai` prints a harmless `SyntaxWarning` when imported.
- Four tests were written alongside their code instead of being watched failing first: the robots.txt HTML/5xx cases and the first location-helper cases.
