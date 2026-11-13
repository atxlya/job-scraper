# R3 — Sitemaps, feeds, notice pages and partial sources — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 12 companies (55 supported in total): SuccessFactors sitemaps (Wipro, HCLTech, EY, Deloitte India), an RSS feed (Zoho), Tata Elxsi's job board, government notice pages (DRDO, ISRO, CDAC, BARC) and title-only partial sources (Cognizant, SAP). Siemens and Uber move to "Not supported".

**Architecture:** Each adapter follows the R1 contract (`list_jobs` / `fetch_detail` → `RawJob`) and registers in `ADAPTERS`. Two shared changes come first: `PoliteClient` checks robots.txt on every redirect hop (SuccessFactors sends missing jobs to a disallowed `/errorpage/`), and a sitemap reader plus "title guessed from the URL" marker, so a slug title never overwrites a real one. Government notices and partial sources are ordinary `RawJob`s marked by `platform_flags` (`notice`, `partial`); the classifier and the alert text read those flags, so nothing else downstream changes.

**Tech Stack:** Python 3.13, httpx via `PoliteClient`, selectolax (HTML), stdlib `xml.etree.ElementTree` (sitemaps, RSS), respx + pytest. React/TypeScript only for one label map.

**Spec:** [docs/DESIGN.md](../../DESIGN.md) §3 (scraping, politeness, accuracy checks), §6 (government notices, partial sources), §11 (testing), §12 (releases). Per-company evidence: [docs/companies.md](../../companies.md) "R3 — +14". Earlier decisions: [R1-notes.md](../R1-notes.md), [R2-notes.md](../R2-notes.md), [R2b-notes.md](../R2b-notes.md). Every endpoint below was probed live on **2026-11-11** through `PoliteClient` (robots.txt checked). The shapes, IDs, titles and status codes quoted are from those responses.

## Decisions this plan makes (the spec is silent or open)

| # | Decision | Why |
|---|---|---|
| D1 | **Siemens → Not supported.** Reason: "Avature RSS feed is a fixed list of 20 old jobs; the HTML search shows 6 jobs a page". | The feed returns the same 20 items (2018–2021) whatever the `folderRecordsPerPage`, `folderOffset`, `folderSort` or keyword parameters; the sitemap has no job URLs; the search page shows 6 of "999+" per page; a job page is 1.2 MB. Agreed with the user on 2026-11-11. |
| D2 | **Uber → Not supported.** Reason: "sitemap lists job IDs only (no titles); job pages are behind Cloudflare". | `jobs.uber.com/en/jobs/sitemap.xml` has 811 `/en/jobs/{id}/` URLs with no slug; job pages answer 403 "Just a moment…". Agreed with the user. |
| D3 | **`PoliteClient` follows redirects itself and checks robots.txt before every hop.** A disallowed hop raises `RobotsDisallowed` and is never fetched. `get(…, follow_redirects=False)` returns the 3xx unfollowed. robots.txt fetches still follow redirects. At most 5 hops. | SuccessFactors answers a missing job with `302 → /errorpage/?errortype=Exception`, and its robots.txt has `Disallow: /error`. The probe's client followed it. This also closes R2b's "redirects are followed without re-checking robots.txt". |
| D4 | **SuccessFactors lists from `https://{host}/sitemap.xml` in both modes.** One response (98–238 KB gzip). `reported_total=None`; `complete` only in full mode. `lastmod` is ignored. | Wipro's and HCLTech's search pages are filled by script from `/services/`, which robots.txt disallows, so the sitemap is their only listing. Deloitte's search reports "of 1921" and the sitemap has 1,921 jobs, and its newest 25 search results were all in the sitemap, so it is current. Every `lastmod` is `2026-11-07`, so it says nothing about a job. |
| D5 | **Sitemap titles are guesses from the URL slug, marked `RawJob.title_from_url=True`.** Ingest never lets such a title replace a stored one. Real titles come from the detail page, which is fetched only for possible tech internships (R1 rule). | Without this, every 30-minute run would turn "Management Trainee" back into "Bengaluru Management Trainee IND 560035" and log a change. Fetching 33,000 detail pages is not an option. |
| D6 | **Tata Elxsi gets its own adapter (`company/tataelxsi`)**, not the notice-page adapter. | It's an ordinary job board (title, locations, date, detail page with description and an Apply link), classified like any other job. "Notice page" is kept for the four government sites. |
| D7 | **Notices use their own internship words.** A job with `platform_flags["notice"]` is an internship when its title matches `notice_internship` (DESIGN §6: intern / trainee / apprentice / JRF / project / summer / fellowship), is not one when it matches `notice_skip` (results, answer keys, shortlists, corrigenda, cancellations…), and is unclear (Gemini) on a `maybe_internship` word. Tech words work as usual. | Most notices on these pages are about existing recruitments ("Provisionally Selected List of JRF…"). Without a skip list they would alert as JRF openings. |
| D8 | **A notice's `description_html` is built from the listing text** (title, description, advertisement number, dates). Notices whose two flags the rules settle skip Gemini; unclear ones go to Gemini with that text. | DESIGN §6 says Gemini decides unclear notices, and the queue skips jobs without text. PDFs are never downloaded (D9), so this is the only text there is. |
| D9 | **PDFs are linked, never downloaded or parsed.** `apply_url` is the notice PDF: read from the list (CDAC, BARC) or from the notice page (DRDO, ISRO). | DESIGN §6 asks only for the PDF link. There is no PDF parser in the stack. |
| D10 | **Notice identity:** DRDO = the notice's URL slug; ISRO = the recruitment page file name (`SACRecruitment21.html`), titled by the first announcement listed for it; CDAC = the link's `dynamicId` or `id` query value, or `ext:` + 12 hex of sha1(title) for links off the site; BARC = the PDF file name (`vacancy27.pdf`). | ISRO lists several announcements per recruitment page (answer keys, panels); one notice per page means one alert per recruitment. CDAC links two different notices to `careers.cdac.in`. |
| D11 | **Notice sources set `allow_empty: true`.** Each notice parser raises `ParseError` when its page marker is missing (see Task 8), so a broken page is still a failure. | A government page with no current notices is normal. |
| D12 | **Partial sources** (Cognizant, SAP) store the slug title and the link, set `platform_flags["partial"]`, never fetch a job page (including the tracked re-check and the dashboard's on-demand fetch), and skip Gemini. Only titles the rules call a tech internship alert, with "ℹ️ Details unavailable — open link". Unclear titles are stored but not alerted. | DESIGN §6. Job pages are Cloudflare challenges. There is no text for Gemini to read. |
| D13 | **Cognizant reads only `global-en` job URLs** (2,091 on 2026-11-11, not the ≈3.3k in companies.md). SAP reads `jobs.sap.com/en/jobs/sitemap.xml` (454). | Cognizant's sitemap repeats every job under 21 locales. |
| D14 | **`rss` adapter (Zoho Recruit format).** `IST` in `pubDate` means +05:30. `?source=RSS` is stripped from links. The description keeps the `<span id="spandesc">` part; `Location:` is read from the prefix. `fetch_detail` re-reads the feed and returns `GONE` when the item is gone. | `parsedate_to_datetime("… IST")` returns a naive time. Zoho's job pages are rendered by script and aren't fetched. |
| D15 | **Alert text:** a notice shows "📄 Government notice — eligibility is in the PDF" and links "Notice PDF" (its `apply_url`, else "Notice" to its `url`). A partial job shows "ℹ️ Details unavailable — open link" and links "Open link". These replace the eligibility lines. | DESIGN §6 wording. Eligibility can't be checked from a title. |
| D16 | **No "Add company" detection for the new adapters.** | A sitemap or notice site can't be recognised from a URL alone. They're added in `sources.yaml`. |
| D17 | **XML is parsed with stdlib `ElementTree`** from bytes, matching tags by local name. The recorder trims XML fixtures (`--keep REGEX`, then `--max-items`). | SuccessFactors uses the `google.com/schemas/sitemap/0.9` namespace, others `sitemaps.org`. Python 3.13's expat guards against entity expansion. Cognizant's sitemap is 7.4 MB. |

## Global Constraints

- Python `>=3.13`, `uv`. `uv run ruff check` and `uv run ruff format --check` are clean at every commit (line length 100). `cd web && npm run check` is clean at every commit that touches `web/`.
- **Every request goes through `PoliteClient`**, and after Task 1 robots.txt is checked before every request and every redirect hop (DESIGN §3). No adapter creates its own httpx client.
- **Never fetched:** job pages on `careers.cognizant.com`, `jobs.sap.com`, `jobs.uber.com` and `jobs.siemens.com`; `careers.cdac.in` (broken TLS chain); any `/services/` or `/errorpage/` path; any PDF (linked only); Zoho job pages.
- **Fixtures are recorded real responses** (`scripts/record_fixture.py`), never hand-written (DESIGN §11). A test may change one field of a loaded fixture to set up a case. Redirect answers have no body; tests serve them as `httpx.Response(302, headers={"Location": …})` with the exact status and `Location` pinned in this plan from the 2026-11-11 probe.
- Titles, IDs and counts quoted from 2026-11-11 may have changed by the time a fixture is recorded. A test then uses the recorded value, and `R3-notes.md` says what changed. A changed *shape* (a missing marker, a different "not found" answer) is a finding to raise, not to code around.
- An adapter raises `ParseError` when a response lacks its expected shape or page marker, and returns `GONE` only for the "not found" answers this plan names per site.
- Times are UTC-aware (`app.adapters.base.utc`). Country codes are ISO 3166 alpha-2. Government notices get `country_codes=["IN"]`.
- `RawJob.platform_flags["intern"]` only from a site field that marks internships. None of R3's sites has one, so R3 sets none. `notice` and `partial` are the only new flags.

## Review Focus

1. **A missing SuccessFactors job** (`302 → /errorpage/?errortype=Exception`) must come back as `GONE` without the error page being requested, not as a `RobotsDisallowed` that leaves the job "detail failed" forever. Test: Task 4, `test_missing_job_is_gone_without_fetching_error_page`.
2. **A slug title from the next sitemap read** must not overwrite the real title a detail page gave, or every run logs a change. Test: Task 2, `test_guessed_title_never_overwrites_stored`.
3. **Notices about existing recruitments** ("Provisionally Selected List of JRF in DYSL-CT, Chennai", "List of Shortlisted Candidates … Project Associate…") must not alert as openings. Test: Task 3, `test_notice_titles`.
4. **Partial sources must never request a job page**, including from the tracked re-check and the dashboard's on-demand fetch, which both call `fetch_detail`. Test: Task 5, `test_never_requests_job_pages`.
5. **DRDO's links are `http://`**, and `http://drdo.gov.in/robots.txt` is unreachable, so an un-upgraded link makes every notice page fail with `RobotsUnavailable`. Test: Task 8a, `test_links_upgraded_to_https`.

---

## File Structure

```
app/http/client.py              robots check per redirect hop; get(…, follow_redirects=True)
scripts/record_fixture.py       --no-follow (prints status + Location); XML trimming (--keep, --max-items); .xml files
app/adapters/base.py            RawJob.title_from_url: bool = False
app/adapters/text.py            + slug_title()
app/adapters/sitemap.py         NEW read_urlset()
app/adapters/successfactors.py  NEW platform adapter (Wipro, HCLTech, EY, Deloitte)
app/adapters/sitemap_partial.py NEW title-only adapter (Cognizant, SAP)
app/adapters/rss.py             NEW Zoho Recruit RSS
app/adapters/notice_page.py     NEW DRDO, ISRO, CDAC, BARC parsers
app/adapters/company/tataelxsi.py NEW
app/adapters/__init__.py        import the new modules
app/pipeline/ingest.py          _merged keeps the stored title when title_from_url
app/pipeline/classify.py        notice rules; Keywords gains notice_internship, notice_skip
config/keywords.yaml            notice_internship, notice_skip lists
app/worker/runner.py            _classify_new: no Gemini for partial jobs and settled notices
app/notify/alerts.py            notice and partial alert lines
config/sources.yaml             12 new companies; Siemens and Uber unsupported
web/src/pages/Sources.tsx       adapter labels
docs/companies.md, docs/DESIGN.md, docs/R3-notes.md (new)
tests/adapters/test_<name>.py, tests/fixtures/<name>/   one per new adapter
```

---

### Task 1: Robots check on every redirect hop; recorder for XML and redirects

**Files:**
- Modify: `app/http/client.py` (`__init__`, `get`, `_request`, `_fetch_robots`), `scripts/record_fixture.py`
- Test: `tests/http/test_client.py`

**Interfaces:**
- Produces:
  - `PoliteClient.get(url, *, params=None, headers=None, follow_redirects: bool = True) -> httpx.Response`. The inner `httpx.AsyncClient` is built with `follow_redirects=False`. `_request` follows `resp.next_request` itself, up to `MAX_REDIRECTS = 5` (then `httpx.TooManyRedirects`). Each hop is robots-checked (`_check_robots`) and paced (`_wait_turn`, retries) like a new request. With `follow_redirects=False` the 3xx response is returned as is. `post_json` follows the same way.
  - `_fetch_robots` passes `follow_redirects=True` for `/robots.txt` (RFC 9309 allows it; Apple's robots.txt redirects).
  - `record_fixture.py`:
    - `--no-follow`: requests with `follow_redirects=False` and prints `status` and `Location`.
    - A response whose content type contains `xml` is saved as `{name}.xml`. When its root's local name is `urlset` (children `url`, key `loc`) or `rss` (children `channel/item`, key `link`), it keeps only children whose key matches `--keep REGEX` (default: all), then the first `--max-items`, and writes the tree back with `ElementTree.tostring`.

- [ ] **Step 1: Write the failing tests** (in `tests/http/test_client.py`, with its `robots()` helper and `respx`):
  - `test_redirect_target_checked_against_robots`: robots `"User-agent: *\nDisallow: /error\n"`; `https://a.com/job/x/1/` → `302` `Location: /errorpage/?errortype=Exception`. `await client.get(...)` raises `RobotsDisallowed`; the `/errorpage/` route was never called.
  - `test_allowed_redirect_followed`: `/job/A/1340802255/` → `302` `Location: /job/A/134372-en_US/` → `200 "ok"`. The response is 200 with `resp.url` ending `134372-en_US/`.
  - `test_follow_redirects_false_returns_3xx`: same 302 with `follow_redirects=False` → `status_code == 302`, `headers["location"] == "/errorpage/?errortype=Exception"`, target not called.
  - `test_redirect_to_other_host_uses_its_robots`: `a.com/x` → `302 https://b.com/y`; b.com's robots disallows `/y` → `RobotsDisallowed`.
  - `test_too_many_redirects`: six chained 302s → `httpx.TooManyRedirects`.
  - `test_robots_redirect_still_followed`: `a.com/robots.txt` → `301 /robots-real.txt` → `"User-agent: *\nDisallow: /private\n"`. A GET of `/private/x` raises `RobotsDisallowed`.
- [ ] **Step 2: Run them to see them fail**
  Run: `uv run pytest tests/http/test_client.py -v`
  Expected: the 6 new tests FAIL (redirects followed by httpx without robots checks; no `follow_redirects` kwarg).
- [ ] **Step 3: Implement** the redirect loop, the kwarg and the robots fetch flag, then the recorder flags.
- [ ] **Step 4: Run the tests to see them pass**
  Run: `uv run pytest -q`
  Expected: everything passes. An existing test that relied on httpx following a redirect by itself is changed to serve each hop.
- [ ] **Step 5: Commit**
  ```bash
  git add app/http/client.py scripts/record_fixture.py tests/http/test_client.py
  git commit -m "feat: check robots.txt on every redirect hop; recorder trims XML"
  ```

### Task 2: Sitemap reader, slug titles, guessed titles never overwrite

**Files:**
- Create: `app/adapters/sitemap.py`, `tests/adapters/test_sitemap.py`
- Modify: `app/adapters/base.py` (`RawJob`), `app/adapters/text.py`, `app/pipeline/ingest.py:_merged`
- Test: `tests/adapters/test_text.py`, `tests/pipeline/test_ingest.py`

**Interfaces:**
- Produces:
  - `RawJob.title_from_url: bool = False`: the title was rebuilt from the URL. `_merged(raw, job)` keeps `job.title` when it is set.
  - `slug_title(slug: str) -> str` in `text.py`: `unquote`, `html.unescape`, `-` and `_` → space, collapse whitespace, strip, upper-case the first character only.
  - `class SitemapUrl(NamedTuple): loc: str; lastmod: str | None`.
  - `async def read_urlset(client: PoliteClient, url: str) -> list[SitemapUrl]`: `GET url`, `raise_for_status()`, `ElementTree.fromstring(resp.content)`. The root's local name must be `urlset`, else `ParseError` (also for bodies that aren't XML). Children are matched by local name (`url`, `loc`, `lastmod`), whatever the namespace.

- [ ] **Step 1: Write the failing tests**
  - `test_slug_title`: `slug_title("Bengaluru-Management-Trainee-IND-560035") == "Bengaluru Management Trainee IND 560035"`; `slug_title("Pune-SOLUTION-ARCHITECT-L1%28CONTRACT%29-IND-411005") == "Pune SOLUTION ARCHITECT L1(CONTRACT) IND 411005"`; `slug_title("software-engineering-internship-trizetto-product-house") == "Software engineering internship trizetto product house"`.
  - `tests/adapters/test_sitemap.py` (fixtures from Task 4 and 5 are recorded here first: `successfactors wipro_sitemap GET https://careers.wipro.com/sitemap.xml --max-items 25` and `sitemap_partial sap_sitemap GET https://jobs.sap.com/en/jobs/sitemap.xml --max-items 25`):
    - `test_reads_both_namespaces`: Wipro's (`google.com/schemas/sitemap/0.9`) and SAP's (`sitemaps.org`) fixtures each give 25 `SitemapUrl`s; the first Wipro `loc` is `https://careers.wipro.com/job/Pune-SOLUTION-ARCHITECT-L1%28CONTRACT%29-IND-411005/1363531455/` with `lastmod == "2026-11-07"`.
    - `test_sitemap_index_raises_parse_error`: `jobs.sap.com/sitemap.xml`'s real `<sitemapindex>` (record `sitemap_partial sap_index GET https://jobs.sap.com/sitemap.xml`) → `ParseError`.
    - `test_html_raises_parse_error`: an HTML body → `ParseError`.
  - `tests/pipeline/test_ingest.py::test_guessed_title_never_overwrites_stored`: a stored job titled "Management Trainee" with a description; ingest a listing `RawJob` with the same `external_id`, `title="Bengaluru Management Trainee IND 560035"`, `title_from_url=True`. The title is unchanged and no `JobChange` row is added.
  - `test_real_title_still_updates`: same with `title_from_url=False` → title updated, one `JobChange` with `"title"`.
- [ ] **Step 2: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_text.py tests/adapters/test_sitemap.py tests/pipeline/test_ingest.py -v`
  Expected: FAIL (ImportError for `slug_title` / `app.adapters.sitemap`; `title_from_url` unknown).
- [ ] **Step 3: Implement** the field, `slug_title`, `read_urlset` and the `_merged` rule.
- [ ] **Step 4: Run the tests to see them pass**
  Run: `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: sitemap reader and URL-slug titles` (with the two fixture folders).

### Task 3: Notice and partial jobs in classification, Gemini queue and alerts

**Files:**
- Modify: `config/keywords.yaml`, `app/pipeline/classify.py` (`Keywords`, `load_keywords`, `classify`), `app/worker/runner.py:_classify_new`, `app/notify/alerts.py` (`format_alert`, `_links`)
- Test: `tests/pipeline/test_classify.py`, `tests/worker/test_runner.py`, `tests/notify/test_alerts.py`

**Interfaces:**
- Produces:
  - `keywords.yaml` gains (same regex-fragment format as the other lists):
    - `notice_internship`: `interns?`, `internships?`, `trainees?`, `apprentice(ship)?s?`, `jrf`, `junior research fellow(ship)?s?`, `fellow(ship)?s?`, `projects?`, `summer`
    - `notice_skip`: `results?`, `answer keys?`, `short-?listed`, `shortlist`, `selected`, `select list`, `selection panel`, `admit cards?`, `call letters?`, `response sheets?`, `cancell?ation`, `corrigendum`, `date extension`, `extension of time`, `schedule of interview`, `interview schedule`, `skill test`, `document verification`
  - `Keywords` gains `notice_internship` and `notice_skip` patterns (a missing list never matches).
  - `classify(raw, kw)`: when `raw.platform_flags.get("notice")`, after removing `not_internship` words: `notice_skip` → `False`; else `notice_internship` → `True`; else `maybe_internship` → `None`; else `False`. `is_tech` is unchanged for every job.
  - `_classify_new`: `analysis_state = "skipped"` also when the job has `platform_flags["partial"]`, or has `platform_flags["notice"]` and neither flag is `None`.
  - `format_alert`: for `notice` jobs the eligibility lines become `["📄 Government notice — eligibility is in the PDF"]` and the first link is `<a href="{apply_url}">Notice PDF</a>` (or `<a href="{url}">Notice</a>` without `apply_url`). For `partial` jobs they become `["ℹ️ Details unavailable — open link"]` and the link is `<a href="{url}">Open link</a>`. A degree-only title still adds its ⚠️ line first. The dashboard link is unchanged.

- [ ] **Step 1: Write the failing tests**
  - `test_notice_titles` (parametrised; `job(title, notice=True)`), with real titles from the 2026-11-11 pages:
    - `"DGRE, Chandigarh invites application for Paid Internship for Engg/Science UG/PG Students"` → `is_internship True`
    - `"Advt No. SAC:02:2026 dated 10.09.2026 - Inviting online applications for the posts of Junior Research Fellows, Research Associate and Project Scientist-I."` → `True`
    - `"Recruitment for Project Staff on Various Contract positions for C-DAC, Chennai through Walk in Interview"` → `True`
    - `"Provisionally Selected List of JRF in DYSL-CT, Chennai"` → `False`
    - `"List of Shortlisted Candidates for the Final Round of Interview for Project Associate- Software Simulator Developer"` → `False`
    - `"CORRIGENDUM - ADVERTISEMENT REF. NO. CORP/JIT/03/2026"` → `False`
    - `"Walk-in-interview for the post of Scientific Assistant/B"` → `False`
    - `"Advt No.ISRO:ICRB:02(EMC-CEPO):2026 dated 28.07.2026 - Selection Panel for the post of Scientist/Engineer 'SC' (Mechanical,Computer Science)"` → `False`
  - `test_notice_flag_does_not_change_ordinary_jobs`: the existing `test_classify_titles` cases give the same answers without the flag (unchanged test, still passing).
  - `tests/worker/test_runner.py::test_partial_and_settled_notices_skip_gemini`: after `_classify_new`, a partial "Software engineering internship trizetto product house" job is `skipped`; a notice "Paid Internship … Engineering" (True/True) is `skipped`; a notice "Paid Internship for UG/PG Students" (True/None) stays `pending`.
  - `tests/notify/test_alerts.py`:
    - `test_partial_alert_says_details_unavailable`: a partial tech internship → text contains `ℹ️ Details unavailable — open link` and `>Open link</a>`, and not `Checking eligibility`.
    - `test_notice_alert_links_pdf`: a notice with `apply_url="https://www.barc.gov.in/careers/vacancy27.pdf"` → contains `📄 Government notice` and `<a href="https://www.barc.gov.in/careers/vacancy27.pdf">Notice PDF</a>`.
    - `test_notice_without_pdf_links_notice_page`: no `apply_url` → `>Notice</a>` pointing at `url`.
- [ ] **Step 2: Run them to see them fail**
  Run: `uv run pytest tests/pipeline/test_classify.py tests/worker/test_runner.py tests/notify/test_alerts.py -v`
  Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the lists, the classifier branch, the skip rule and the alert lines.
- [ ] **Step 4: Run the tests to see them pass**
  Run: `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: notice and partial jobs in classification and alerts`.

### Task 4: SuccessFactors sitemap adapter

**Files:** Create `app/adapters/successfactors.py`, `tests/adapters/test_successfactors.py`. Fixtures in `tests/fixtures/successfactors/`. Modify `app/adapters/__init__.py`.

**Interfaces:**
- `successfactors` (`name = "successfactors"`). cfg `{"host": "careers.wipro.com"}`.
- Listing: `read_urlset(client, f"https://{host}/sitemap.xml")`. A job URL matches `^https://{host}/(?:[a-z_]+/)?job/(?P<slug>[^/]+)/(?P<id>\d+)/$` (EY has `/ey/job/`, `/sgv/job/` and `/eylaw_at/job/`; all are kept). Other URLs are skipped.
  - `RawJob(external_id=id, title=slug_title(slug), url=loc, title_from_url=True)`. `reported_total=None`; `complete = mode == "full"`.
  - Counts on 2026-11-11: Wipro 7,071, HCLTech 15,096, EY 8,924, Deloitte 1,921.
- Detail: `client.get(job.url, follow_redirects=False)`:
  - `200` → parse.
  - `3xx` whose `Location` path starts with `/errorpage` → `GONE` (no request to it). Any other `3xx` → `client.get(urljoin(job.url, location))` and parse its 200. Wipro and HCLTech redirect every job this way, e.g. `/job/Bengaluru-Management-Trainee-IND-560035/1340802255/` → `302 /job/Bengaluru-Management-Trainee-IND-560035/134372-en_US/`.
  - `404`/`410` → `GONE`. Anything else → `raise_for_status()`.
- Parse (selectolax):
  - `title` = text of the first `[itemprop="title"]` (stripped). None → `ParseError`.
  - `description_html` = inner HTML of `[itemprop="description"]`.
  - `posted_at`: `meta[itemprop="datePosted"]` `content` (`"Tue Nov 03 00:00:00 UTC 2026"`, format `"%a %b %d %H:%M:%S UTC %Y"`, UTC). Otherwise the `span.joblayouttoken-label` "Posting Start Date:" followed by its value span (`"10/27/26"`, `"%m/%d/%y"`).
  - `locations`: `[meta[itemprop="streetAddress"] content]` (`"Noida, IN"`, `"Belgrade, RS, 11070"`). Otherwise the "City:" and "State/Province:" token values joined by `", "` (`"Bengaluru, Karnataka"`). HCLTech pages have neither, so `[]`.
  - `country_codes = country_codes(locations)` ∪ the second comma part of `streetAddress` when it is an alpha-2 code pycountry knows.
  - `apply_url=None` (the apply path `/talentcommunity/apply/` is disallowed); `title_from_url=False`; `external_id` and `url` kept from the listing job.

- [ ] **Step 1: Record fixtures** (`uv run python scripts/record_fixture.py successfactors …`): `wipro_sitemap` (Task 2), `hcltech_sitemap GET https://careers.hcltech.com/sitemap.xml --max-items 25`, `ey_sitemap GET https://careers.ey.com/sitemap.xml --keep "/(ey|sgv)/job/" --max-items 25`, `deloitte_job GET https://southasiacareers.deloitte.com/job/Noida-Intern-Talent-Acquisition-Noida-Talent/61228644/`, `ey_job GET https://careers.ey.com/ey/job/Belgrade-Quant-Intern-in-EY-Risk-Consulting-11070/1450762633/`, `wipro_job GET https://careers.wipro.com/job/Bengaluru-Management-Trainee-IND-560035/134372-en_US/`, `hcltech_job GET https://careers.hcltech.com/job/Trainee-Voice/150770-en_US/`. If a job has gone by then, take any current job URL from the sitemap whose slug contains "Intern" or "Trainee", and use its values in the tests.
- [ ] **Step 2: Write the failing tests** (robots served as the real SuccessFactors file: `Disallow: /applybutton/ … /services/ … /error …`):
  - `test_parses_sitemap`: Wipro fixture → 25 jobs; the first has `external_id == "1363531455"`, `title == "Pune SOLUTION ARCHITECT L1(CONTRACT) IND 411005"`, `title_from_url is True`. `complete` is True in full mode and False in incremental.
  - `test_ey_keeps_other_site_paths`: every EY fixture URL becomes a job, including `/sgv/job/` ones.
  - `test_detail_microdata` (Deloitte): `title == "Intern | Talent Acquisition | Noida | Talent"`, `posted_at == datetime(2026, 11, 3, tzinfo=UTC)`, `locations == ["Noida, IN"]`, `country_codes == ["IN"]`, description contains `"Requirement is for an Intern in Operate Hiring Team."`.
  - `test_detail_follows_allowed_redirect` (Wipro): the `1340802255` URL answers `302` with `Location: /job/Bengaluru-Management-Trainee-IND-560035/134372-en_US/`, which serves `wipro_job`. `title == "Management Trainee"`, `locations == ["Bengaluru, Karnataka"]`, `country_codes == ["IN"]`, `posted_at == datetime(2026, 10, 27, tzinfo=UTC)`.
  - `test_detail_title_and_description_only` (HCLTech): `title == "Trainee-Voice"`, `locations == []`, `posted_at is None`, description contains `"handle calls"`.
  - `test_missing_job_is_gone_without_fetching_error_page`: `302` `Location: /errorpage/?errortype=Exception` → `GONE`; a respx route for `/errorpage/` is not called.
  - `test_page_without_title_raises_parse_error`: serve `hcltech_sitemap`'s bytes as a job page → `ParseError`.
- [ ] **Step 3: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_successfactors.py -v`
  Expected: FAIL (module not found).
- [ ] **Step 4: Implement** and register.
- [ ] **Step 5: Run the tests to see them pass**, then commit `feat: successfactors sitemap adapter`.

### Task 5: Partial sitemap adapter (Cognizant, SAP)

**Files:** Create `app/adapters/sitemap_partial.py`, `tests/adapters/test_sitemap_partial.py`. Fixtures in `tests/fixtures/sitemap_partial/`.

**Interfaces:**
- `sitemap_partial` (`name = "sitemap_partial"`). cfg `{"sitemap": URL, "job_url": REGEX}` where the regex has `id` and `slug` groups:
  - Cognizant: `https://careers.cognizant.com/sitemap.xml`, `^https://careers\.cognizant\.com/global-en/jobs/(?P<id>\d+)/(?P<slug>[^/]+)/$` (D13).
  - SAP: `https://jobs.sap.com/en/jobs/sitemap.xml`, `^https://jobs\.sap\.com/en/jobs/(?P<id>\d+)/(?P<slug>[^/]+)/$`.
- Listing: `read_urlset`; URLs that don't match are skipped; duplicate IDs are kept once. `RawJob(external_id=id, title=slug_title(slug), url=loc, platform_flags={"partial": True})` with `title_from_url=False` (the slug is the only title, so a renamed slug should update it). `lastmod` is not a posting date and is ignored. `reported_total=None`; `complete = mode == "full"`.
- `fetch_detail` returns the job unchanged and makes **no request** (D12). Closing relies on the 2-sweep rule.

- [ ] **Step 1: Record fixtures:** `sap_sitemap` (Task 2) and `cognizant_sitemap GET https://careers.cognizant.com/sitemap.xml --keep "/(global-en|india-en)/jobs/" --max-items 40` (keeps some `india-en` and `/global-en/jobs/` index URLs that must be skipped).
- [ ] **Step 2: Write the failing tests:**
  - `test_cognizant_keeps_global_en_jobs`: every job URL matches the Cognizant pattern; `len(jobs)` equals the fixture's distinct matching IDs; no `india-en` URL is a job.
  - `test_sap_titles_from_slug`: the job `744000160974349` has `title == "Sap ixp intern technical support"`, `platform_flags == {"partial": True}`, `description_html is None`.
  - `test_never_requests_job_pages`: respx routes for both job hosts' job paths; `fetch_detail` returns the same job and neither route is called.
  - `test_complete_only_in_full`.
- [ ] **Step 3: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_sitemap_partial.py -v`
  Expected: FAIL.
- [ ] **Step 4: Implement** and register.
- [ ] **Step 5: Run the tests to see them pass**, then commit `feat: title-only sitemap adapter for partial sources`.

### Task 6: RSS adapter (Zoho)

**Files:** Create `app/adapters/rss.py`, `tests/adapters/test_rss.py`. Fixture `tests/fixtures/rss/zoho.xml`.

**Interfaces:**
- `rss` (`name = "rss"`, `listing_has_details = True`). cfg `{"url": "https://careers.zohocorp.com/jobs/Careers/rss"}`. robots.txt allows `/jobs/*` and ends with `Disallow: /`.
- Listing: `GET url`; root local name `rss` with a `channel`, else `ParseError`. 9 items on 2026-11-11, posted 2022–2025 (Zoho reuses standing postings).
- Mapping per `item`:
  - `external_id` = `guid` text (`"193779000024446019"`), or the link without its query when `guid` is missing.
  - `title = html.unescape(title)` (`"Content&#x2f;Technical Writers"` → `"Content/Technical Writers"`).
  - `url` = `link` without `?source=RSS`.
  - `description` starts `"Category: Technology <br><br>Location: Tamil Nadu Tamil Nadu India <br><br><br><span id=\"spandesc\">…"` and ends with an `<a …>Details</a>` link. `locations = [the text after "Location:" up to the next "<"]` stripped; `employment_type=None`; `description_html` = the `<span id="spandesc">…</span>` element's outer HTML (the whole description when it has none).
  - `country_codes(locations)` (→ `["IN"]`).
  - `posted_at`: `pubDate` with a trailing ` IST` replaced by ` +0530`, then `email.utils.parsedate_to_datetime`, then `utc()`.
- `reported_total=None`; `complete = mode == "full"`.
- `fetch_detail` re-reads the feed and returns the matching item, or `GONE` when it is no longer listed.

- [ ] **Step 1: Record** `rss zoho GET https://careers.zohocorp.com/jobs/Careers/rss`.
- [ ] **Step 2: Write the failing tests:**
  - `test_parses_feed`: 9 jobs. The first: `external_id == "193779000024446019"`, `title == "Software Developers"`, `url == "https://careers.zohocorp.com/jobs/Careers/193779000024446019/Software-Developers"`, `locations == ["Tamil Nadu Tamil Nadu India"]`, `country_codes == ["IN"]`; its description contains `"Design and develop high-volume"` and not `"Category:"` or `"Details</a>"`.
  - `test_title_entities_unescaped`: the second job's title is `"Content/Technical Writers"`.
  - `test_ist_pubdate`: the first job's `posted_at == datetime(2022, 6, 24, 6, 30, tzinfo=UTC)`.
  - `test_feed_allowed_by_real_robots`: serve the rules from Zoho's real robots.txt, `"User-agent: *\nAllow: /recruit/downloadrssfeed\nAllow: /jobs\nAllow: /jobs/\nAllow: /jobs/*\nDisallow: /\n"` → the feed is fetched.
  - `test_detail_gone_when_not_in_feed`.
  - `test_not_rss_raises_parse_error`.
- [ ] **Step 3: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_rss.py -v`
  Expected: FAIL.
- [ ] **Step 4: Implement** and register.
- [ ] **Step 5: Run the tests to see them pass**, then commit `feat: rss adapter (zoho recruit)`.

### Task 7: Tata Elxsi

**Files:** Create `app/adapters/company/tataelxsi.py`, `tests/adapters/test_tataelxsi.py`. Fixtures in `tests/fixtures/tataelxsi/`.

**Interfaces:**
- `tataelxsi` (`name = "tataelxsi"`). cfg `{}`.
- Listing: `GET https://www.tataelxsi.com/careers/job-openings?page=N`. Page marker: `div#job_listing`, else `ParseError`. 8 cards a page, newest first (page 1: 05 Nov 2026, 20 Oct, 19 Oct…); 11 pages on 2026-11-11, and page 12 has no cards.
  - Full mode reads page 1, takes the largest `?page=N` in its pagination links, and reads pages 2..N. Incremental mode reads page 1. `reported_total=None`; `complete = mode == "full"` and every page parsed.
  - Card `div.jjbcdeo1`: `h5` (a job code like `"RFH/07609"`, or a repeat of the title), `h3` title, `div.jjbcdeo11 p` = `"Bangalore / Chennai / Hyderabad | 5 - 10 years | B.E, B.Tech, MCA, M.E, M.Tech | JAVA Developer"`, date `div.jjbcdeo12 p` (`"05 Nov 2026"`, `"%d %b %Y"`), link `a.jknmre`.
  - Mapping: `external_id` = the link's last path part (`"java-developer"`); `title` = `h3`; `url` = link; `locations` = the first `|` part split on `" / "`; `country_codes(locations)`; `posted_at`.
- Detail: `client.get(url, follow_redirects=False)`. A `3xx` → `GONE` (a missing slug answers `302 Location: https://www.tataelxsi.com`; the homepage isn't requested). `200`: `title = div.jbpam h2`, `description_html` = inner HTML of `div.jbpam1`, `apply_url = a.japlynw` href (`https://oneelxsi.ramcoes.com/rvw/PortalBroadBeanCalling.aspx?…`). The other fields (ID, URL, locations, date) are kept from the listing job. No `div.jbpam` → `ParseError`.

- [ ] **Step 1: Record:** `page_1 GET "https://www.tataelxsi.com/careers/job-openings?page=1"`, `page_11 … ?page=11`, `job GET https://www.tataelxsi.com/careers/job-openings/java-developer`, `home GET https://www.tataelxsi.com/`.
- [ ] **Step 2: Write the failing tests:** `test_parses_cards` (8 jobs; the first is `java-developer`, `"JAVA Developer"`, `["Bangalore", "Chennai", "Hyderabad"]`, `["IN"]`, `datetime(2026, 11, 5, tzinfo=UTC)`); `test_full_reads_every_page` (pages 1..11 requested; page_1 served for 1–10 and page_11 for 11); `test_incremental_reads_page_one`; `test_detail_page` (description contains `"Key Skills Required"`, `apply_url` starts with `https://oneelxsi.ramcoes.com/`); `test_missing_redirect_is_gone`; `test_home_page_raises_parse_error` (`home` served as the listing).
- [ ] **Step 3: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_tataelxsi.py -v`
  Expected: FAIL.
- [ ] **Step 4: Implement** and register.
- [ ] **Step 5: Run the tests to see them pass**, then commit `feat: tata elxsi adapter`.

### Task 8: Government notice pages — DRDO, ISRO, CDAC, BARC

Four subtasks (8a–8d) in one adapter, each with the same five steps: record → failing tests → run (FAIL) → implement → run (PASS) → commit `feat: notice page — <site>`.

**Files:** Create `app/adapters/notice_page.py`, `tests/adapters/test_notice_page.py`. Fixtures in `tests/fixtures/notice_page/`.

**Interfaces (shared):**
- `notice_page` (`name = "notice_page"`). cfg `{"site": "drdo" | "isro" | "cdac" | "barc", "allow_empty": true}` (D11).
- `PARSERS: dict[str, Callable[[str], list[RawJob]]]` maps the site to a function that parses the listing HTML. Each site has a `LIST_URL`.
- Listing: one `GET LIST_URL` in both modes. `reported_total=None`; `complete = mode == "full"`. Duplicate `external_id`s are kept once, first wins.
- Every notice: `platform_flags={"notice": True}`, `country_codes=["IN"]`, `locations=[]`, links made absolute against the page URL. Titles are whitespace-collapsed with U+2060 and U+200B removed (BARC's "Walk-⁠in-⁠Interview" contains U+2060).
- `description_html = join_sections([(None, f"<p>{escaped title}</p>"), ("Advertisement No", …), ("Published", …), ("Last date", …), (None, listing description html)])`, using only the parts a site has (D8).
- `fetch_detail`: DRDO and ISRO as below. CDAC and BARC return the job unchanged with no request (the PDF link is already in the list).

- **8a DRDO.** `LIST_URL = https://drdo.gov.in/drdo/en/offerings/vacancies`. robots.txt answers 404 (no rules).
  - Marker: `<title>` starts with `"Vacancies |"`, else `ParseError`. 9 boxes on 2026-11-11.
  - Box `div.vacanciess-box`: title `.vacanciess-title`; description `.vacanciess-desc` (inner HTML); advertisement no `.vacanciess-advertisment-no-content`; published `.vacanciess-date-publish-content time[datetime]` (`"2026-11-10T12:00:00Z"` → `posted_at`); start date `.vacanciess-start-date-content`; end date `.vacanciess-due-date-content` text (`"06/12/2026"`); link `.vacanciess-view-node a[href]`.
  - Links come as `http://drdo.gov.in/…`; rewrite the scheme to `https` (Review Focus 5). `external_id` = the link's last path part; `url` = the https link.
  - Detail: `GET url`. `apply_url` = the first `a[href]` containing `/sites/default/files/vacancy/` made absolute (e.g. `https://drdo.gov.in/drdo/sites/default/files/vacancy/advtDGRE10112026.pdf`). A missing notice answers **200** with `<title>no-such-notice-xyz | Defence Research…`: `GONE` when the `<title>` text before `" | "` equals the URL's last path part. A page without a PDF otherwise returns the job unchanged.
  - Record: `drdo_list GET https://drdo.gov.in/drdo/en/offerings/vacancies`, `drdo_notice GET https://drdo.gov.in/drdo/en/offerings/vacancies/dgre-chandigarh-invites-application-paid-internship-enggscience-ugpg-students`, `drdo_missing GET https://drdo.gov.in/drdo/en/offerings/vacancies/no-such-notice-xyz`.
  - Tests: `test_drdo_parses_boxes` (9 notices; the DGRE one has `external_id == "dgre-chandigarh-invites-application-paid-internship-enggscience-ugpg-students"`, `posted_at == datetime(2026, 11, 10, 12, tzinfo=UTC)`, description contains `"DGRE/DRPM/TCHR/5205/Voc Trg/2026-01"` and `"06/12/2026"`); `test_links_upgraded_to_https` (every `url` starts with `https://drdo.gov.in/`); `test_drdo_detail_finds_pdf`; `test_drdo_soft_404_is_gone`; `test_drdo_wrong_page_raises_parse_error` (serve `drdo_notice` as the list).
- **8b ISRO.** `LIST_URL = https://www.isro.gov.in/Careers.html`. robots.txt answers 404.
  - Marker: `<title>` text stripped equals `"Careers"`, else `ParseError`.
  - Each `td.news a[href]` whose `href` matches `(?i)Recruitment[\w-]*\.html$` is an announcement (38 in 41 `td.news` cells on 2026-11-11, on 17 distinct pages). Rows without a link are skipped. Its text is the `title` attribute, or the link text with a trailing `"Read More"` removed.
  - One notice per `href` (D10): `external_id` = the file name, `title` = the first announcement listed for it, `url` = the absolute page URL.
  - Detail: `GET url`. `404` → `GONE` (real: `NoSuchRecruitment99.html` answers 404). `apply_url` = the first `a[href]` containing `/media_isro/pdf/`, absolute (e.g. `https://www.isro.gov.in/media_isro/pdf/recruitmentNotice/2026/Sept/SAC_02_2026_dated_09092026.pdf`).
  - Record: `isro_list GET https://www.isro.gov.in/Careers.html`, `isro_notice GET https://www.isro.gov.in/SACRecruitment21.html`, `isro_missing GET https://www.isro.gov.in/NoSuchRecruitment99.html` (served with 404).
  - Tests: `test_isro_one_notice_per_page` (count == distinct matching hrefs in the fixture; `SACRecruitment21.html`'s title is `"Advt No. SAC:02:2026 dated 10.09.2026 - Inviting online applications for the posts of Junior Research Fellows, Research Associate and Project Scientist-I."`; `CareerOpportunities.html` is not a notice); `test_isro_detail_finds_pdf`; `test_isro_missing_is_gone`.
- **8c CDAC.** `LIST_URL = https://www.cdac.in/index.aspx?id=current_jobs`. robots.txt: `Allow: /`.
  - Marker: an `h3` with text `"Current Openings"` inside `div#content`, else `ParseError`.
  - Every `a[href]` inside `div#content` with non-empty text is a notice, except links whose `id` query value is `print_page`, `career`, `job_archive_jobs` or `profile`.
  - `title` = the link text. When the enclosing `<p>` has a `<strong>` that isn't inside this link and its text differs, `title = f"{strong text} — {link text}"`.
  - `external_id` (D10): the `dynamicId` query value (`"CORRIGENDUM-ADVT-CORP-JIT-03-2026.pdf"`), else the `id` value (`"ca_cdac_chennai_recruitment_2026"`), else for other hosts `"ext:" + sha1(title)[:12]`. `url` = the absolute link; `apply_url = url` when it ends in `.pdf` or has `id=pdf_`. Links to `careers.cdac.in` are stored but never fetched.
  - Record: `cdac_list GET "https://www.cdac.in/index.aspx?id=current_jobs"`.
  - Tests: `test_cdac_parses_links` (the IDs above; the two `careers.cdac.in` notices have different `ext:` IDs; nav links are skipped; PDF notices have `apply_url == url`); `test_cdac_strong_heading_prefixes_link` (the `Walk-In-Positions-PMS-PE.pdf` notice's title starts with `"Walk-In Interview for Various Positions at C-DAC CINE: Advt. No. CINE/REC/2026/06 (Guwahati, Assam) — "`); `test_cdac_detail_makes_no_request`.
- **8d BARC.** `LIST_URL = https://www.barc.gov.in/careers/recruitment.html`. robots.txt allows it.
  - Marker: a `table` whose header row has `"Advertisement No."`, `"Title"`, `"Last Date"`, `"Details"`, else `ParseError`. 5 rows on 2026-11-11.
  - Each `tbody tr`: advertisement no (cell 1); `title` = cell 2's text before any `<br>` or `<b>` (the "Click Here to Download Form" part isn't title); last date (cell 3, `"16-Nov-2026"`); PDF = cell 4's `a[href]` (`vacancy27.pdf`).
  - `external_id` = the PDF file name; `url = apply_url` = the absolute PDF URL (`https://www.barc.gov.in/careers/vacancy27.pdf`). The application-form link (`vacancyform27.pdf`) isn't a notice.
  - Record: `barc_list GET https://www.barc.gov.in/careers/recruitment.html`.
  - Tests: `test_barc_parses_table` (IDs `vacancy24.pdf`…`vacancy28.pdf`; `vacancy27.pdf` is titled `"Walk-in-Interview for the post of Radiographer"` with description containing `"MD"` and `"16-Nov-2026"`); `test_barc_missing_table_raises_parse_error` (serve `cdac_list`).

### Task 9: Registry, dashboard labels, docs and the live check

**Files:** Modify `config/sources.yaml`, `tests/core/test_registry.py:58-59`, `web/src/pages/Sources.tsx`, `docs/companies.md`, `docs/DESIGN.md` (§1, §2, §3, §12). Create `docs/R3-notes.md`.

**Interfaces:**
- `sources.yaml`:
  - `wipro`, `hcltech`, `ey`, `deloitte-india` (adapter `successfactors`, `host` = `careers.wipro.com`, `careers.hcltech.com`, `careers.ey.com`, `southasiacareers.deloitte.com`).
  - `zoho` (`rss`, `url` from Task 6); `tataelxsi` (`tataelxsi`, `{}`).
  - `drdo`, `isro`, `cdac`, `barc` (`notice_page`, `{site: …, allow_empty: true}`).
  - `cognizant`, `sap` (`sitemap_partial`, cfg from Task 5).
  - `siemens` and `uber` as `supported: false` with the D1/D2 reasons.
  - The header's config-key comment lists the new adapters' keys.
- `Sources.tsx` labels: `successfactors: "SuccessFactors"`, `rss: "RSS feed"`, `notice_page: "Notice page"`, `sitemap_partial: "Sitemap (titles only)"`, `tataelxsi: "Tata Elxsi (own site)"`.

- [ ] **Step 1: Write the failing test:** `test_shipped_registry_valid` expects **55** supported and **16** unsupported, each with a reason.
- [ ] **Step 2: Run it to see it fail**
  Run: `uv run pytest tests/core/test_registry.py -v`
  Expected: FAIL (43 ≠ 55).
- [ ] **Step 3: Fill in the YAML and the labels.**
- [ ] **Step 4: Run every check, then the live check**
  - Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && (cd web && npm run check)`. Expected: all pass.
  - Run `uv run python -m app.cli live-check --source <key> --mode full` for each of the 12 new sources. Expected: `OK` for each (a notice source may be OK with 0). A failure is fixed in its adapter task's file, and its fixture re-recorded if the site changed.
  - Run `uv run python -m app.cli run-once --mode full --source <key>` into a scratch database for `ey` and `drdo`. Expected: possible internships get a real title and description (EY) or a PDF `apply_url` (DRDO), and a second run logs no title changes.
  - Then `uv run python -m app.cli live-check --mode incremental` for all sources. Expected: every source OK, the 43 earlier ones included.
- [ ] **Step 5: Update the docs and commit**
  - `companies.md`: replace the R3 table with what was built (adapter, URL, job counts, the "not found" answer per site, Cognizant's 2,091 global-en jobs, Wipro/HCLTech's script-only search, DRDO's http links, Zoho's IST dates, Tata Elxsi as its own adapter). Move Siemens and Uber to "Not supported" with their reasons. Quote Zoho's robots.txt (it ends with `Disallow: /` and allows `/jobs/*`).
  - `DESIGN.md`: §1 64 → 62 companies; §2 14 → 16 unsupported; §6 partial sources are "Cognizant, SAP" (Uber removed); §12 R3 55, R4 62. §3's platform list is unchanged (RSS stays, for Zoho).
  - `R3-notes.md`, in R2b-notes' format: status table (tests, live check per source with job counts), decisions made during the build, what's not checked yet, and anything left for later.
  - Commit: `feat: register R3 companies; docs and live-check results`.
