# R2b build notes: Lever, Greenhouse and company adapters

What was built, what was checked, and where the build differed from the [plan](plans/2026-11-11-r2b-adapters.md). Branch `r2b-adapters`, 2026-11-11.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 397 passing (was 295) |
| Web tests (`cd web && npm run check`) | 40 passing; type-check clean |
| Independent review of the whole branch | "With fixes": five fixed (below), the rest listed under "Left for later" |
| Live check, full mode, each new source | All 15 OK (table below) |
| Live check, incremental mode, all 43 companies (47 sources) | 0 failed, the 28 R1 companies included |
| **Not yet checked** | The new sources running on the Pi; Zerodha with real openings (none today, so its parser has no non-empty fixture); the first full sweep's Gemini backlog from the new internships |

**Full-mode live check, 2026-11-11** (jobs read / total the site reports):

| Source | Jobs | Total | | Source | Jobs | Total |
|---|---|---|---|---|---|---|
| paytm (Lever) | 201 | — | | apple-interns | 130 | 130 |
| meesho (Lever) | 50 | — | | atlassian | 341 | — |
| cred (Lever) | 14 | — | | amd | 1,308 | 1,308 |
| razorpay (Greenhouse) | 25 | 25 | | ibm-interns | 232 | 232 |
| groww (Greenhouse) | 9 | 9 | | capgemini-india | 707 | 707 |
| inmobi (Greenhouse) | 78 | 78 | | phonepe | 152 | — |
| amazon | 2,556 | 2,556 | | swiggy | 195 | 195 |
| zerodha | 0 | 0 (allowed) | | | | |

"—" means the site reports no total for that listing.

## What changed for everyone

- **robots.txt `Crawl-delay` is honoured** (capped at 30 s). AMD asks for 5 s. Any R1 site that sets it is now paced to match.
- **Listings that already carry the description skip the detail fetch.** That's Lever, Greenhouse's full sweep, Amazon, Atlassian, AMD, Capgemini, IBM and Zerodha.
- **`allow_empty: true`** on a source makes 0 jobs healthy: no live-check failure, no "count dropped" warning, and an empty listing may close jobs through the usual 2-sweep rule. Only Zerodha uses it.
- **"Add company" detects Lever and Greenhouse URLs**, and its error message names them.
- **EU Lever boards (`jobs.eu.lever.co`) aren't detected.** They use another API host, which isn't supported yet.
- `scripts/record_fixture.py` takes `--header "K: V"` (needed for SmartRecruiters' JSON answer).

## Decisions made during the build

Each line gives the change from the plan, why, and what it costs if wrong. The plan's own decisions (D1–D12) are in the plan.

- **PhonePe and Zerodha jobs default to India** when the location text isn't a city the country list knows (e.g. "Tirupati"). Both hire only in India. *Cost:* a rare non-India job would be tagged India.
- **Apple locations use the location's `name` when `city` is empty**, and the country also comes from Apple's `countryID` (`iso-country-CHN` → CN). The real data has `city: ""` with `name: "Shanghai"`. *Cost:* none.
- **Capgemini reads every page on every run.** Its pages start at 1 and aren't newest-first, so page 1 alone could miss new jobs. That's about 8 requests every 30 minutes.
- **Swiggy's `r` and `h` are Remote and Hybrid**, read from the site's own script (`r === 1` shows a "Remote" tag).
- **A removed SmartRecruiters posting answers 404 (HTML)**, and a removed Apple job answers 200 with no job data. Both count as "gone".
- **Commits:** Lever + Greenhouse went in one commit, as did the four listing-only adapters, because they share files.

## Fixed after the review
- **Apple: a changed job page no longer counts as "removed".** Only a page with no job route at all is "gone"; any other missing data is a parse error. Before, a small Apple site change would have silently dropped every new Apple internship.
- **"Intern" no longer matches "International" or "Internal"** in Lever commitments and Capgemini contract types, so those can't cause false internship alerts.
- **A listing that ends early is no longer "complete".** Amazon, IBM, AMD and Capgemini used to call the run complete when the last page came back empty, which could count toward closing jobs.
- **One odd Swiggy row is skipped** instead of failing the whole source. A response where no row has a usable link still fails.
- **"Add company" stopped detecting EU Lever URLs** (see above), because the test fetch could never work.

## Left for later

> **2026-11-11:** the code items below were fixed or found already fixed on branch `fix-deferred`; see [deferred-fixes-notes.md](deferred-fixes-notes.md). What's still open is listed there.

- **Zerodha:** record a real non-empty `/api/jobs` answer once openings appear, and add a parsing test for it. The field names come from the site's script, not from a real job.
- **Polling size:** Paytm's Lever listing (≈3 MB) and Atlassian's (≈2.4 MB) are read in full every 30 minutes, because neither has a smaller form.
- **IBM descriptions are search snippets**, so Gemini's eligibility check sees only a summary.
- **Amazon** has no internship filter. Its ≈2,100 India jobs are scraped so India internships aren't missed; internships elsewhere come only from the "intern" keyword search.
- **SmartRecruiters company pages** (`jobs.smartrecruiters.com/{Company}`) might bring Freshworks, Bosch and ServiceNow back. Not tried.
- From the review (minor): the SmartRecruiters ID match doesn't check the host; Apple's page regex could stop early on an escaped `");` (a parse error, not wrong data); the "removed" fixtures are made-up IDs, so record a really expired PhonePe or Swiggy posting when one drops off; Zerodha re-reads its whole list per job in the tracked run; `allow_empty` turns off every drop warning, not only drops to zero; IBM's snippets are boilerplate, so Gemini requests for them can only return "unknown"; there's no test for Capgemini reading every page in incremental mode; a Lever list with no content leaves an empty heading.
- From the review (R1 behaviour, unchanged): redirects are followed without re-checking robots.txt; one failing job fails a source's whole tracked re-check.
