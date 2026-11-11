# R3 build notes: sitemaps, feeds and notice pages

What was built, what was checked, and where the build differed from the [plan](superpowers/plans/2026-11-11-r3-sitemaps-feeds-notices.md). Branch `r3-adapters`, 2026-11-11.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 468 passing (was 397) |
| Web tests (`cd web && npm run check`) | 40 passing; type-check clean |
| Registry | 55 supported companies, 16 unsupported (Siemens and Uber added) |
| Live check, full mode, each new source | All 12 OK (table below) |
| Live check, incremental mode, all sources | 0 failed of 59 sources (the 47 earlier ones and the 12 new ones) |
| `run-once` on a scratch database | `ey` and `drdo`, full mode, twice each: no title changes (`job_changes` stayed empty). EY stored 8,934 jobs, 118 of them possible internships with a real title and description; DRDO's paid-internship notices carry a PDF `apply_url`. EY's second run saw 7 new jobs (the site changed in between) |
| **Not yet checked** | The new sources running on the Pi; a real alert from a notice or partial job (none was sent: alerts and Gemini were off); the first sweep's Gemini backlog from the new internships; Zoho, ISRO or BARC with different data than today's |

**Full-mode live check, 2026-11-11** (jobs read; the sitemap and feed sources report no total, so the check can't compare counts for them. Deloitte's search page shows "of 1921", but the adapter reads the sitemap, not that page):

| Source | Jobs | | Source | Jobs |
|---|---|---|---|---|
| wipro | 7,070 | | drdo | 9 |
| hcltech | 15,094 | | isro | 17 |
| ey | 8,934 | | cdac | 32 |
| deloitte-india | 1,928 | | barc | 5 |
| zoho | 9 | | cognizant | 2,085 |
| tataelxsi | 83 | | sap | 454 |

## What changed for everyone

- **`PoliteClient` follows redirects itself and checks robots.txt before every hop** (at most 5). A disallowed hop raises `RobotsDisallowed` and is never fetched; `get(..., follow_redirects=False)` returns the 3xx. This closes R2b's "redirects are followed without re-checking robots.txt".
- **Titles guessed from a URL slug** (`RawJob.title_from_url`) never replace a stored title, so a sitemap job's real title (read from its detail page) isn't turned back into the slug guess.
- **Notice and partial jobs** have their own classification and alert text: notices use their own internship words and skip list; partial jobs alert only on a tech-internship title, with "Details unavailable - open link"; neither is sent to Gemini unless the rules leave a notice unclear.
- `scripts/record_fixture.py` records XML (`--keep REGEX`, `--max-items`) and takes `--no-follow`.

## Decisions made during the build

The plan's own decisions (D1-D17) are in the plan. These were made while building:

- **Tata Elxsi: an empty card date gives no posted date.** Page 11 really has cards with `<p></p>` for the date. A non-empty date that can't be read is still a parse error. *Cost:* none.
- **Task 3's runner test uses "Paid Internship for Engineering Students" and "Paid Internship for UG/PG Students"** for the titles the plan left out. *Cost:* one test's wording.
- **Extra EY fixture:** `ey_sitemap_sgv` holds three real `/sgv/job/` URLs so the test that other site paths are kept isn't vacuous.
- **Cognizant fixture** holds both `global-en` and `india-en` job URLs, so the test that only `global-en` is read uses real data.
- **`run-once` checks ran against a scratch SQLite database** with Telegram and Gemini variables unset.

## Differences found live

- **CDAC:** the Chennai notice (`ca_cdac_chennai_recruitment_2026`) is now inside an HTML comment, and only one `careers.cdac.in` link is live. The test for distinct `ext:` identities uses the page's two off-site links.
- **DRDO:** a new first notice (DMRL Hyderabad, 11/11/2026); the DGRE notice is still there with the expected values.
- **Tata Elxsi:** page 11 has empty dates (above).
- **Cognizant:** 2,091 `global-en` jobs when probed and 2,085 unique ones in the live check (not about 3.3k, which counted every locale).
- **EY:** the sitemap also lists `/sgv/job/` and `/eylaw_at/job/` URLs; they are kept.

## Fixed after the review
- **SuccessFactors: a missing job behind two redirects is "gone".** Wipro and HCLTech redirect each `/job/.../{id}/` to an `-en_US` URL, which can itself redirect to `/errorpage/`. The adapter now follows up to 5 hops by hand and answers "gone" as soon as a hop points at `/errorpage`, without requesting it. Before, the robots check on that second hop raised an error and aborted tracked runs. More than 5 hops is an error.
- **Tata Elxsi: only a redirect to the home page is "gone".** Any other redirect is followed (through the polite client) and parsed.
- **Notice titles with "Engg"** (DRDO's "Paid Internship for Engg/Science UG/PG Students") now count as tech: `engg` was added to the `tech` keywords.
- **Cleanup:** removed two dead `if False` expressions (SuccessFactors description, RSS description). No behaviour change.
- **Docs:** the RSS source does have a per-job lookup (Zoho re-reads the feed and answers "gone" when the item is missing); the live-check note about totals is corrected above.
- **Kept on purpose:** a bare "project" on a notice still counts as internship-like (DESIGN section 6), so C-DAC "Project Engineer" walk-in notices will alert. Change this if it gets noisy.

## Left for later

From the per-task reviews (all minor):

- **SuccessFactors:** a dead `... if False else _inner(desc_node)` expression (successfactors.py ~122); the second redirect hop follows redirects, so a redirect to `/errorpage/` on hop 2 raises `RobotsDisallowed` instead of "gone"; an empty `Location` refetches the same URL.
- **RSS:** the same dead `if False` expression (rss.py ~57); one item without title or link fails the whole feed; no tests for the guid fallback, a non-IST `pubDate` or a bad one.
- **Partial sources:** a bad `job_url` regex gives a raw `re.error`, and a missing `id` or `slug` group an `IndexError` at the first sweep (no config validation); the duplicate-ID test doesn't assert the duplicate was injected.
- **Tata Elxsi:** any 3xx counts as "gone", so an http-to-https or trailing-slash redirect would close a live job; `external_id` raises `IndexError` on a link with no slash; the pager regex scans the whole page.
- **Notice pages:** the `http://` to `https://` rewrite applies to any host or position; DRDO's detail PDF link isn't upgraded when absolute; CDAC application-form links become separate notices that share the advertisement's heading (possible double alert); an unknown `site` raises `KeyError` in the listing but is silent in the detail fetch; BARC relies on `<thead>`, and a "no vacancies" row with a colspan would be a parse error instead of an empty list; ISRO could yield an empty title.
- **Classification:** `app/core/eligibility.py` ignores the notice and partial flags, so the dashboard badge shows "Not checked" for them; the notice skip words "selected" and "results" could drop a real opening (plan-mandated).
- **Fetch layer:** `trim_xml` registers a nested default namespace as the root's and has no unit tests; `--no-follow` is ignored for POST; robots.txt fetches use httpx's limit of 20 redirects, not 5; no tests for same-host hop pacing or exactly five hops.
- **Sitemap helpers:** the HTTP-error path of `read_urlset` and entries without `<loc>` are untested.
- **Wipro and HCLTech** can only be listed from the sitemap (their search is script-only and under a disallowed `/services/`), and every `lastmod` is the same date, so new jobs can't be dated.
- **Cognizant and SAP** keep only slug titles; unclear titles are stored but not alerted.
