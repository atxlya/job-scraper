# R4 build notes: the last seven sites

What was built, what was checked, and where the build differed from the [plan](superpowers/plans/2026-11-11-r4-headless.md). Branch `r4-adapters`, 2026-11-11.

R4 was planned as the "headless (Playwright)" release. Checking each site through `PoliteClient` showed that none needs a browser: six give their jobs as server HTML, a form POST or the JSON the page itself calls, and Urban Company's only source is disallowed by robots.txt. So no Playwright was added: no new dependency, no Chromium in the Docker image, nothing extra running on the Pi.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 534 passing (was 472) |
| Web tests (`cd web && npm run check`) | 40 passing; type-check clean |
| Registry | 61 supported companies, 17 unsupported (Urban Company added) |
| Live check, full mode, each new source | All 6 OK (table below) |
| Independent review of the whole branch | "With fixes": four fixed (below), the rest listed under "Left for later" |
| Live check, incremental mode, all sources | 0 failed of 65 sources (the 59 earlier ones and the 6 new ones), before and after the review fixes |
| `run-once` on a scratch database | `techmahindra` and `jio-tech`, full mode, twice each, Telegram and Gemini unset: 502 and 247 jobs stored, no title changes on the second run; every Tech Mahindra job has its card description |
| **Not yet checked** | The new sources running on the Pi; what a really removed job looks like on LTIMindtree, Jio, Reliance and Tech Mahindra (none has been seen, so those close jobs only through the 2-sweep rule); a real alert from one of the new sources |

**Full-mode live check, 2026-11-11** (jobs read / total the site reports):

| Source | Jobs | Total | | Source | Jobs | Total |
|---|---|---|---|---|---|---|
| techmahindra | 502 | — | | sharechat | 11 | — |
| ltimindtree | 620 | 620 | | jio-tech | 247 | 247 |
| myntra | 51 | 51 | | reliance | 44 | — |

"—" means the site reports no total for that listing. Tech Mahindra had 501 jobs when probed and 502 at the live check.

## What changed for everyone

- **`PoliteClient.post_form`** sends form POSTs with the same robots check, pacing and retries as every other request.
- **`app/adapters/aspnet.py`** does ASP.NET WebForms postbacks (Tech Mahindra, Jio, Reliance). A postback that doesn't answer 200 (a rejected form answers `302 → /error.aspx`) is a parse error, so a broken page walk fails the run instead of looking like "no more jobs".
- `scripts/record_fixture.py` takes `--form K=V`, `--step SPEC` (records the answer after one or more postbacks, as the raw bytes the site sent) and `--drop-keys` (removes employee contact fields from ShareChat's JSON before it is saved).

## Decisions made during the build

The plan's own decisions (D1-D13) are in the plan. These were made while building:

- **Myntra: `APPRENTICESHIP` also sets the internship flag.** The real list has one (`2455903149`, "Apprentice"); DESIGN §5 counts apprentices as internships. *Cost:* none; the tech rules still decide alerts.
- **Reliance's bad-key page has an empty posted date, not a missing one.** The plan expected the "My Profile" page to lack `#MainContent_lblPostedDate`; it has every field, empty. The job-page parser (shared with Jio) now needs a non-empty posted date. *Cost:* a real job page with no date would be stored without a description and retried next run.
- **Jio's Apprentice category sets the internship flag** (`intern_categories: ["0227"]`). Its 24 jobs are titled "JC Field Engineer_DET", which the title rules read as "not an internship", so without the flag they would never be checked or alerted. DESIGN §5 lets a site's own facet set the flag (like Workday's `workerSubType`). *Cost:* these are field-engineer apprenticeships for diploma holders; if Gemini calls them tech, up to 24 alerts arrive on the first run's summary and later one per new posting.
- **The 25-rows-a-page walk is one function** (`walk_pages`) shared by Jio and Reliance.
- **The recorder saves the raw postback answer**, not a re-serialised page, so `--step` fixtures stay real recorded bytes.

## Fixed after the review

- **Employee names and emails are no longer in the fixtures.** Myntra's search and job answers carry a `recruiter` (full name and @myntra.com email, 7 people); they were re-recorded with `--drop-keys recruiter`. ShareChat's job answer (`coordinatorEmpName`, here "MyNextHire System") and RippleHire's company block (placeholder contacts) were re-recorded the same way. `tests/adapters/test_fixture_privacy.py` checks every R4 JSON fixture for those keys and for email addresses. The first recordings are still in this branch's history (commit 44ce591); a squash merge keeps them out of `main`. No adapter ever stored these fields.
- **A Tech Mahindra full run can no longer stop early and call itself complete.** If a page's pager still offers later pages ("Last", ">>" or a higher number) but no link to the next one, the run fails. Before, it ended after that page with `complete=True`, and two such nights would have closed about 490 open jobs.
- **The same guard for Jio and Reliance:** a page with a pager but no "Showing N of M Pages" text fails the full run instead of reading page 1 only. This matters most for Reliance, which has no site total to compare against.
- **Tech Mahindra card text is no longer escaped twice** (a skill set "P&C" showed as `P&amp;amp;C`). It now reads exactly as the site shows it.

## Left for later

> **2026-11-11:** the code items below were fixed or found already fixed on branch `fix-deferred`; see [deferred-fixes-notes.md](deferred-fixes-notes.md). What's still open is listed there.

- **careers.ltm.com** (SuccessFactors, 47 jobs, 2 in India) isn't read; its `/sitemap.xml` is an RSS feed that neither the `successfactors` nor the `rss` adapter reads.
- **Jio's other categories** (≈30,000 freelance, sales and operations jobs) aren't read.
- **ShareChat links** go to the careers page, not the job: per-job links are a base64 JSON context built by the site's script.
- **Tech Mahindra** has no public job page, so its "description" is the card (skills, experience, location).
- From the review (minor): Tech Mahindra's incremental run doesn't check that the "Last" postback landed on a later page (if not, alerts wait for the nightly run); the first listing GETs on Jio, Reliance and Tech Mahindra follow redirects, so a redirect to `/error.aspx` would be fetched (and then fail to parse); ShareChat treats any 417 as "gone" without checking its message; a non-JSON 200 from a Myntra or ShareChat job call fails the source run instead of one job; a tracked re-check stops at its first failing job (existing runner behaviour, more likely now that LTIMindtree, Jio and Reliance answer missing jobs with errors); the page walk doesn't check that the page total stays the same; Myntra asks for its workspace id again on every job call.
- **If a future site really needs a browser**, it would need: Playwright Chromium in the image (≈400–500 MB on arm64), a route handler that checks every navigation and the page's own requests against the same robots cache and per-host pacing and blocks images, fonts and media, one browser run at a time with a timeout, and the browser closed after each source.
