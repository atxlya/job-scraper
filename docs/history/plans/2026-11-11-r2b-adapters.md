# R2b — Lever, Greenhouse and company adapters — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 15 companies (43 supported in total): Lever (Paytm, Meesho, CRED), Greenhouse (Razorpay, Groww, InMobi), and company adapters for Amazon, Apple, Atlassian, AMD, IBM, Capgemini, PhonePe, Swiggy and Zerodha. Meta and Goldman Sachs move to "Not supported". "Add company" learns to detect Lever and Greenhouse URLs.

**Architecture:** Each adapter follows the R1 contract (`list_jobs` / `fetch_detail` → `RawJob`) and registers itself in `ADAPTERS`. Most new listings already carry the full description, so a new adapter flag lets the worker skip the detail fetch for them. Three small shared changes come first: that flag, honouring robots.txt `Crawl-delay`, and an `allow_empty` source option (for Zerodha, which has 0 openings today). PhonePe and Swiggy list jobs on their own endpoints but link to SmartRecruiters job pages, which one shared helper reads.

**Tech Stack:** Python 3.13, httpx via `PoliteClient`, pydantic, selectolax (not needed by any new adapter), respx + pytest for tests. React/TypeScript only for two label maps.

**Spec:** [docs/DESIGN.md](../../DESIGN.md) §3 (scraping, politeness, accuracy checks), §11 (testing), §12 (releases). Per-company evidence: [docs/companies.md](../../companies.md) "R2 — +17". R1 and R2a decisions: [R1-notes.md](../R1-notes.md), [R2-notes.md](../R2-notes.md). Every endpoint below was probed live on **2026-11-11** through `PoliteClient` (robots.txt checked). The shapes quoted are from those responses.

## Decisions this plan makes (the spec is silent or open)

| # | Decision | Why |
|---|---|---|
| D1 | **Meta → Not supported.** Reason: "metacareers.com robots.txt says automated collection is prohibited without written permission". | The robots rules allow job pages, but the file's own notice forbids scraping. Agreed with the user on 2026-11-11. |
| D2 | **Goldman Sachs → Not supported.** Reason: "higher.gs.com has no internships; the campus portal hasn't been found". | `roleSearch` with `EARLY_CAREER` returns 6 roles, none of them internships. Agreed with the user. |
| D3 | **Zerodha is built with `allow_empty: true`.** A successful empty answer is healthy: `live-check` passes, there's no "count dropped" warning, and an empty complete listing may close jobs through the normal 2-sweep rule. | `careers.zerodha.com/api/jobs` answers `{"count":0,"data":[],"success":true}` today. Agreed with the user. |
| D4 | **New adapter flag `listing_has_details: ClassVar[bool]`** (default False). When it's True and the listing already has `description_html`, the worker doesn't call `fetch_detail` for that job. | Lever, Greenhouse (full mode), Amazon, Atlassian, AMD, Capgemini and IBM listings carry the whole posting. |
| D5 | **robots.txt `Crawl-delay` is honoured**, per host: wait `max(min_interval_s, crawl_delay)`, capped at 30 s. | AMD's robots.txt says `crawl-delay: 5`. A capped value stops a typo from stalling a source. |
| D6 | **IBM is listing-only.** `careers.ibm.com` is never fetched (AWS WAF challenge). The description is the search snippet, and `fetch_detail` makes no request. | companies.md: "don't touch it". |
| D7 | **Amazon uses two overlapping queries**: `base_query=intern` (worldwide) and `normalized_country_code[]=IND` (all India jobs). `reported_total = sum(hits) − duplicates seen`. | Amazon ignores `job_type[]`, `business_category[]` and `team[]`, and `is_intern` / `university_job` are always null. The subtraction keeps the count check exact while the queries overlap. |
| D8 | **SmartRecruiters job pages** (`jobs.smartrecruiters.com/{Company}/{id}-{slug}`) are read with `Accept: application/json`, which returns the posting as JSON. `api.smartrecruiters.com` is never used. | The API host's robots.txt allows only LinkedInBot; the jobs host has no robots.txt (404). |
| D9 | **Sources whose listing is one response** (Lever, Greenhouse, Atlassian, PhonePe, Swiggy, Zerodha) make the same request in both modes. `complete` is True only in full mode. | There is nothing smaller to poll. Greenhouse's incremental run leaves out `content=true` (a much smaller response). Paytm's Lever listing (≈3 MB) is the largest. |
| D10 | **Paged listings poll page 1 in incremental mode** only when the order is newest-first (Apple with `sort=newest`, IBM by `dcdate desc`, Amazon `sort=recent`). Capgemini's order gets checked while recording: page 1 if newest-first, otherwise every page. AMD polls only its intern category. | Keeps 30-minute polling small. |
| D11 | **Plain-text descriptions** (Apple, IBM) become HTML through one helper, `text_to_html`, which escapes the text and keeps paragraphs and bullet lists. | The dashboard and Gemini expect HTML, and `nh3` still sanitises it. |
| D12 | **"Add company" detects Lever and Greenhouse** URLs. These close R2a's D2. | Both now have adapters. |

## Global Constraints

- Python `>=3.13`, `uv`. `uv run ruff check` and `uv run ruff format --check` are clean at every commit (line length 100). `cd web && npm run check` is clean at every commit that touches `web/`.
- **Every request goes through `PoliteClient`**, so robots.txt is checked before every request (DESIGN §3). No adapter creates its own httpx client.
- **Never fetched:** `careers.ibm.com`, `api.smartrecruiters.com`, `metacareers.com`, `higher.gs.com`.
- **Fixtures are recorded real responses** (`scripts/record_fixture.py`), never hand-written (DESIGN §11). A test may change one field of a loaded fixture (for example, set a total) to set up a case. It never invents a job.
- An adapter raises `ParseError` when the response lacks its expected top-level keys, and returns `GONE` only for a real "not found" answer.
- Times are UTC-aware (`app.adapters.base.utc`). Country codes are ISO 3166 alpha-2.
- `RawJob.platform_flags["intern"] = True` only from a site field that marks internships. Titles are left to the rule classifier.

## Review Focus

1. **A one-response board that suddenly returns an empty list** (for example, Lever for a renamed site) must not close every job, unless the source has `allow_empty` (D3). Test: Task 1, `test_empty_listing_closes_only_when_allowed`.
2. **Amazon's two queries overlapping** (an India internship appears in both) must not mark the run "partial". Test: Task 5, `test_overlapping_queries_count_duplicates_once`.
3. **Greenhouse `content` is HTML-escaped** (`&lt;div&gt;…`). Stored descriptions must be real HTML, not escaped text the dashboard shows as tags. Test: Task 3, `test_content_is_unescaped`.
4. **A removed SmartRecruiters or Apple posting** must come back as `GONE`, not as a `ParseError` that retries forever. Tests: Task 4, `test_sr_missing_is_gone`; Task 6, `test_detail_missing_is_gone`.
5. **IBM job links** must never be fetched, including by the dashboard's on-demand description fetch and the tracked re-check. Test: Task 7d, `test_ibm_never_requests_careers_site`.

---

## File Structure

```
app/adapters/
  base.py                 + listing_has_details on the Adapter protocol (docs only; read with getattr)
  text.py                 NEW text_to_html(), from_ms(), join_sections()
  lever.py                NEW platform adapter
  greenhouse.py           NEW platform adapter
  smartrecruiters_page.py NEW fetch_posting(), apply_posting() (shared by PhonePe, Swiggy)
  company/amazon.py, apple.py, atlassian.py, amd.py, ibm.py, capgemini.py,
          phonepe.py, swiggy.py, zerodha.py   NEW
  __init__.py             import the new modules
app/http/robots.py        + Robots.crawl_delay(agent)
app/http/client.py        per-host wait uses the crawl delay
app/worker/runner.py      skip fetch_detail when listing_has_details and a description exists
app/sources/checks.py     evaluate(result, mode, cfg=None): allow_empty
app/sources/detect.py     + Lever, Greenhouse
app/pipeline/ingest.py    empty complete listing may close jobs when allow_empty
app/notify/health.py      no "count dropped" warning when allow_empty
app/cli.py, app/api/sources.py   pass cfg to evaluate()
scripts/record_fixture.py + --header K:V (repeatable)
config/sources.yaml       15 new companies; Meta and Goldman unsupported
web/src/pages/Sources.tsx, web/src/components/AddCompanyDialog.tsx   labels
docs/companies.md, docs/DESIGN.md, docs/R2b-notes.md (new)
tests/adapters/test_<name>.py, tests/fixtures/<name>/   one per new adapter
```

---

### Task 1: Shared groundwork — detail skip, allow_empty, text helpers, recorder headers

**Files:**
- Create: `app/adapters/text.py`, `tests/adapters/test_text.py`, `tests/notify/test_health.py`, `tests/sources/test_checks.py`
- Modify: `app/adapters/base.py` (protocol docstring + attribute), `app/worker/runner.py:104-118`, `app/sources/checks.py`, `app/pipeline/ingest.py:185`, `app/notify/health.py:_problem`, `app/cli.py:45`, `app/api/sources.py:103`, `scripts/record_fixture.py`
- Test: `tests/worker/test_runner.py`, `tests/pipeline/test_ingest.py`

**Interfaces:**
- Produces:
  - `Adapter.listing_has_details: ClassVar[bool]`. The runner reads it as `getattr(adapter, "listing_has_details", False)`, so the R1 adapters need no change.
  - `text_to_html(text: str | None) -> str | None`: `None`/blank → `None`. Escapes with `html.escape`, then works block by block (blocks are separated by blank lines). Inside a block, each run of lines starting with `- `, `• ` or `* ` becomes `<ul><li>…</li></ul>`, and each run of other lines becomes one `<p>` with `<br>` between its lines.
  - `from_ms(ms: int | str | None) -> datetime | None`: epoch milliseconds → UTC-aware datetime. Accepts digits as a string and Microsoft's `/Date(1787616000000)/`.
  - `join_sections(parts: list[tuple[str | None, str | None]]) -> str | None`: each `(heading, html)` with a non-blank body becomes `<h3>{escaped heading}</h3>{html}` (just `html` when the heading is None), joined with `\n`. `None` when every body is blank.
  - `evaluate(result: ListingResult, mode: str, cfg: dict | None = None) -> list[str]`: with `cfg.get("allow_empty")`, 0 jobs is not a problem.
  - `record_fixture.py … --header "Accept: application/json"` (repeatable). Headers are passed to `client.get` / `client.post_json`.

- [ ] **Step 1: Write the failing tests**
  - `tests/adapters/test_text.py`:
    - `test_text_to_html_paragraphs_and_lists`: `text_to_html("What we offer\n- Learn\n- Grow\n\nBe <bold>")` == `"<p>What we offer</p><ul><li>Learn</li><li>Grow</li></ul><p>Be &lt;bold&gt;</p>"`.
    - `test_text_to_html_blank_is_none`: `text_to_html("  \n")` is `None`.
    - `test_from_ms_forms`: `from_ms(1783043640931)`, `from_ms("1783043640931")` and `from_ms("/Date(1783043640931)/")` all equal `datetime(2026, 7, 3, 1, 54, 0, 931000, tzinfo=UTC)`. `from_ms(None)` is `None`.
    - `test_join_sections_skips_blank`: `join_sections([("About", "<p>a</p>"), ("Empty", " "), (None, "<p>b</p>")])` == `"<h3>About</h3><p>a</p>\n<p>b</p>"`.
  - `tests/worker/test_runner.py::test_listing_details_skip_detail_fetch`: register a stub adapter with `listing_has_details = True` whose listing returns a tech-internship `RawJob` that has `description_html`. Its `fetch_detail` raises `AssertionError`. Run incremental. The job is stored with that description.
  - `tests/worker/test_runner.py::test_listing_details_without_description_still_fetches`: same stub, but the listing job has no description. `fetch_detail` is called once.
  - `tests/sources/test_checks.py::test_zero_jobs_fails_unless_allow_empty`: `evaluate(ListingResult(jobs=[], reported_total=0, complete=True), "full")` == `["0 jobs returned"]`. With `cfg={"allow_empty": True}` → `[]`.
  - `tests/pipeline/test_ingest.py::test_empty_listing_closes_only_when_allowed`: one open job seen in an earlier full sweep. Two complete full sweeps with `jobs=[]`: the job stays open on a plain source, and is closed on a source whose `config={"allow_empty": True}`.
  - `tests/notify/test_health.py::test_no_drop_warning_when_allow_empty`: previous full run found 2 jobs, this one 0. `_problem` returns the "dropped" text for a plain source and `None` when `source.config["allow_empty"]` is set.
- [ ] **Step 2: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_text.py tests/worker/test_runner.py tests/sources/test_checks.py tests/pipeline/test_ingest.py tests/notify/test_health.py -v`
  Expected: the new tests FAIL (ImportError for `app.adapters.text`, assertion failures for the rest).
- [ ] **Step 3: Implement**
  - The runner's candidate loop skips the detail fetch when `getattr(adapter, "listing_has_details", False) and raw.description_html`.
  - `ingest`'s empty-listing guard becomes `if not result.jobs and open_jobs and not (source.config or {}).get("allow_empty")`.
  - `health._problem` skips the drop check when `(source.config or {}).get("allow_empty")`.
  - `cli.live_check` passes `src.config` to `evaluate`, and `api/sources.py` passes the detected config.
- [ ] **Step 4: Run the tests to see them pass**
  Run: `uv run pytest -q`
  Expected: everything passes (295 + the new ones).
- [ ] **Step 5: Commit**
  ```bash
  git add app tests scripts
  git commit -m "feat: listing-detail skip, allow_empty sources, text helpers"
  ```

### Task 2: Honour robots.txt Crawl-delay

**Files:**
- Modify: `app/http/robots.py`, `app/http/client.py:_wait_turn`
- Test: `tests/http/test_robots.py`, `tests/http/test_client.py`

**Interfaces:**
- Produces: `Robots.crawl_delay(user_agent: str) -> float | None`. It reads `Crawl-delay` (case-insensitive) from the group that applies to the agent, using the same group choice as `allowed()`. A missing or unparseable value → `None`.
- `PoliteClient` waits `min(30.0, max(self.min_interval_s, crawl_delay or 0))` between requests to a host. `MAX_CRAWL_DELAY_S = 30.0`.

- [ ] **Step 1: Write the failing tests**
  - `test_crawl_delay_parsed`: AMD's real file (`"User-agent: *\nAllow: /\nSitemap: http://careers.amd.com/sitemap.xml\ncrawl-delay: 5\n"`) → `crawl_delay("job-scraper/0.1")` == `5.0`. A file without the line → `None`. `"Crawl-delay: soon"` → `None`.
  - `test_client_waits_for_crawl_delay` (in `test_client.py`, with the fake clock and sleep the existing tests use): robots.txt has `Crawl-delay: 5` and `min_interval_s=1`. Two GETs to the host → the recorded sleep before the second is `5`.
  - `test_crawl_delay_capped`: `Crawl-delay: 3600` → the wait is `30`.
- [ ] **Step 2: Run them to see them fail**
  Run: `uv run pytest tests/http -v`
  Expected: the 3 new tests FAIL.
- [ ] **Step 3: Implement** the parser field and the per-host wait. The robots entry is already cached per host, so read the delay from it.
- [ ] **Step 4: Run the tests to see them pass**
  Run: `uv run pytest tests/http -v`
  Expected: PASS.
- [ ] **Step 5: Commit** `feat: honour robots.txt crawl-delay`.

### Task 3: Lever and Greenhouse platform adapters, with URL detection

Two subtasks (3a Lever, 3b Greenhouse), each with the same steps.

**Files:** Create `app/adapters/lever.py`, `app/adapters/greenhouse.py`, `tests/adapters/test_lever.py`, `tests/adapters/test_greenhouse.py`. Fixtures in `tests/fixtures/lever/`, `tests/fixtures/greenhouse/`. Modify `app/adapters/__init__.py`, `app/sources/detect.py`, `tests/sources/test_detect.py`.

**Interfaces:**
- `lever` (`name = "lever"`, `listing_has_details = True`). cfg `{"site": "paytm"}`.
  - Listing: `GET https://api.lever.co/v0/postings/{site}?mode=json` returns a JSON **list** of every posting. Anything else → `ParseError`. `reported_total=None`.
  - Mapping: `external_id=id`; `title=text`; `url=hostedUrl`; `apply_url=applyUrl`; `locations=categories.allLocations` or `[categories.location]`; `country_codes = country_codes(locations) ∪ {country}` (Lever's `country` is already alpha-2, e.g. `IN`); `remote_type = workplaceType` when it is `onsite`/`hybrid`/`remote` (`unspecified` → None); `employment_type=categories.commitment`; `posted_at=from_ms(createdAt)`.
  - `description_html = join_sections([(None, description), *((l.text, f"<ul>{l.content}</ul>") for l in lists), (None, additional)])`.
  - `platform_flags={"intern": True}` when `commitment` matches `(?i)\bintern`.
  - Detail: `GET https://api.lever.co/v0/postings/{site}/{id}?mode=json`. 404 → `GONE`. Otherwise the same mapping as a listing item.
- `greenhouse` (`name = "greenhouse"`, `listing_has_details = True`). cfg `{"board": "groww"}`.
  - Listing: `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs`, plus `?content=true` **in full mode only** (D9). The answer has `{"jobs": [...], "meta": {"total": N}}`. `reported_total=meta.total`.
  - Mapping: `external_id=str(id)`; `title`; `url=absolute_url`; `locations=[location.name]` plus `offices[].name` values not already listed; `country_codes(locations)`; `posted_at=first_published`; `employment_type` = the `metadata` entry named `"Employment Type"` (its `value`, or the first element when it's a list); `description_html=html.unescape(content)` when present.
  - Detail: `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}`. 404 → `GONE`.
- `detect(url)` gains:
  - Lever: host `jobs.lever.co` or `jobs.eu.lever.co` with first path part `{site}`, or `api.lever.co/v0/postings/{site}` → `Detected("lever", {"site": site}, site)`.
  - Greenhouse: hosts `boards.greenhouse.io`, `job-boards.greenhouse.io`, `job-boards.eu.greenhouse.io` with first path part `{board}` (skipping `embed`, where the board is the `for=` query value), or `boards-api.greenhouse.io/v1/boards/{board}` → `Detected("greenhouse", {"board": board}, board)`.

- [ ] **Step 1: Record fixtures** (`uv run python scripts/record_fixture.py …`):
  - `lever paytm_interns GET "https://api.lever.co/v0/postings/paytm?mode=json&commitment=Intern"` (6 postings on 2026-11-11), `lever cred GET "https://api.lever.co/v0/postings/cred?mode=json"`, one detail `lever paytm_detail GET "https://api.lever.co/v0/postings/paytm/9eed4fec-73f7-4114-a5d3-b2f689c92e8c?mode=json"` (live on 2026-11-11; any current Paytm ID works), and `lever missing GET "https://api.lever.co/v0/postings/paytm/00000000-0000-0000-0000-000000000000?mode=json"` (a real 404 `{"ok":false,"error":"Document not found"}`).
  - `greenhouse groww_full GET "https://boards-api.greenhouse.io/v1/boards/groww/jobs?content=true"` (9 jobs), `greenhouse groww_light GET "https://boards-api.greenhouse.io/v1/boards/groww/jobs"`, `greenhouse inmobi GET "https://boards-api.greenhouse.io/v1/boards/inmobi/jobs?content=true"` (has `"Employment Type"` metadata), one detail, and `greenhouse missing GET "https://boards-api.greenhouse.io/v1/boards/groww/jobs/1"` (404 `{"status":404,"error":"Job not found"}`).
  The recorder writes the body only. Tests serve the `missing` fixtures with status 404.
- [ ] **Step 2: Write the failing tests** (respx serving the fixtures; robots.txt mocked to 404, as in `test_oracle_hcm.py`):
  - Lever: `test_parses_listing` (one `RawJob` per list item; the first maps `external_id`, `url == hostedUrl`, `apply_url == applyUrl`, `posted_at == from_ms(createdAt)`, `country_codes` includes `country`); `test_intern_commitment_sets_flag` (every job in `paytm_interns` has `platform_flags == {"intern": True}`; no `cred` job does); `test_lists_and_additional_in_description` (for a posting with non-empty `lists`, `description_html` contains `<h3>{lists[0].text}</h3>`); `test_complete_only_in_full`; `test_detail_missing_is_gone`; `test_not_a_list_raises_parse_error` (body `{"ok": false}` with status 200).
  - Greenhouse: `test_parses_listing` (`len(jobs) == meta.total == 9`, `reported_total == 9`); `test_content_is_unescaped` (every `description_html` starts with `<` and contains no `&lt;`); `test_incremental_omits_content` (request URL has no `content` param; jobs have `description_html is None`); `test_full_requests_content`; `test_employment_type_from_metadata` (an InMobi job → `"Direct Consultant"`); `test_detail_missing_is_gone`; `test_missing_jobs_key_raises_parse_error`.
  - Detection (`tests/sources/test_detect.py`): `https://jobs.lever.co/paytm` and `https://jobs.lever.co/paytm/9eed4fec-73f7-4114-a5d3-b2f689c92e8c` → `Detected("lever", {"site": "paytm"}, "paytm")`; `https://job-boards.eu.greenhouse.io/groww/jobs/4970739101` and `https://boards.greenhouse.io/embed/job_board?for=inmobi` → greenhouse with boards `groww` / `inmobi`; `https://jobs.lever.co/` → `None`.
- [ ] **Step 3: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_lever.py tests/adapters/test_greenhouse.py tests/sources/test_detect.py -v`
  Expected: FAIL (module not found / detection returns `None`).
- [ ] **Step 4: Implement** both adapters, register them in `app/adapters/__init__.py`, and extend `detect()`.
- [ ] **Step 5: Run the tests to see them pass, then commit**
  Run: `uv run pytest tests/adapters tests/sources -v`. Expected: PASS.
  Commit `feat: lever adapter and detection`, then `feat: greenhouse adapter and detection`.

### Task 4: SmartRecruiters job pages, PhonePe and Swiggy

**Files:** Create `app/adapters/smartrecruiters_page.py`, `app/adapters/company/phonepe.py`, `app/adapters/company/swiggy.py`, `tests/adapters/test_smartrecruiters_page.py`, `tests/adapters/test_phonepe.py`, `tests/adapters/test_swiggy.py`. Fixtures in `tests/fixtures/smartrecruiters/`, `phonepe/`, `swiggy/`.

**Interfaces:**
- `smartrecruiters_page.fetch_posting(client: PoliteClient, url: str) -> dict | Gone`: `GET url` with header `Accept: application/json`. A 404 or 410 → `GONE`. Whatever the real "removed" answer is when recorded (Step 1) also → `GONE`. A 200 that isn't JSON with `jobTitle` and `content.sections` → `ParseError`.
- `smartrecruiters_page.apply_posting(job: RawJob, posting: dict) -> RawJob`:
  - `description_html = join_sections` over `content.sections` in the order `companyDescription`, `jobDescription`, `qualifications`, `additionalInformation`, each as `(section.title, section.text)`.
  - `posted_at = postedDate`; `employment_type = employmentType`; `apply_url = applyUrl`; `locations = [jobAdLocation]` when the job had none.
- `SR_ID = re.compile(r"/(\d+)-[^/?#]*")`: the posting ID inside a SmartRecruiters job URL.
- `phonepe` (`name = "phonepe"`). cfg `{}`.
  - Listing: `GET https://www.phonepe.com/apollo/job-postings/latest.json` → `{"fetchedAt", "results", "totalCount"}`. Keep rows with `status == "PUBLIC"` and an `applyUrl` that matches `SR_ID` (153 of 955 on 2026-11-11).
  - Mapping: `external_id` = the matched ID; `url = applyUrl`; `title`; `locations=[location]`; `employment_type=type`; `platform_flags={"intern": True}` when `type == "Intern"`.
  - `reported_total=None`. `complete = mode == "full" and len(results) == totalCount`.
  - Detail: `fetch_posting(job.url)` → `apply_posting`.
- `swiggy` (`name = "swiggy"`). cfg `{}`.
  - Listing: `GET https://careers.swiggy.in/api/jobs.json` → `{"generatedAt", "jobs", "total"}`. Items use one-letter keys: `t` title, `l` location (`"Puri, India"`), `c` city, `b` business unit, `e` employment type, `d` epoch ms, `u` SmartRecruiters URL, `r`/`h` flags (0/1).
  - Mapping: `external_id` from `u` via `SR_ID`; `url=u`; `locations=[l]`; `posted_at=from_ms(d)`; `employment_type=e or None`.
  - `r` and `h`: while recording, read what the site's script (`careers.swiggy.in/assets/index-*.js`) uses them for. If they are remote/hybrid, map them to `remote_type`. Otherwise ignore them. Write down which in companies.md.
  - `reported_total=total`.
  - Detail: `fetch_posting(job.url)` → `apply_posting`.

- [ ] **Step 1: Record fixtures:**
  - `phonepe latest GET https://www.phonepe.com/apollo/job-postings/latest.json --max-items 400`. That keeps enough rows to include PUBLIC ones; check the trimmed file still has at least one `"type": "Intern"` PUBLIC row (there was 1 on 2026-11-11, `1000000000002543-intern-company-secretary`), and raise `--max-items` if it doesn't.
  - `swiggy jobs GET https://careers.swiggy.in/api/jobs.json`.
  - `smartrecruiters posting GET https://jobs.smartrecruiters.com/PHONEPELIMITED/1000000000002543-intern-company-secretary --header "Accept: application/json"`.
  - `smartrecruiters missing GET https://jobs.smartrecruiters.com/PHONEPELIMITED/1000000000000000-missing --header "Accept: application/json"`. Write down the status and body it returns; that answer is what `fetch_posting` treats as `GONE`.
- [ ] **Step 2: Write the failing tests:**
  - `test_sr_posting_fills_description` (four `<h3>` headings in section order; `posted_at == 2026-09-18T07:07:50.839Z`; `employment_type == "Intern"`); `test_sr_missing_is_gone` (served with the recorded status); `test_sr_html_answer_raises_parse_error`; `test_sr_sends_json_accept` (the request had `Accept: application/json`).
  - PhonePe: `test_keeps_only_public_with_id` (every job came from a PUBLIC row; count equals PUBLIC rows with a matching `applyUrl`); `test_intern_type_sets_flag`; `test_incomplete_when_results_short` (drop one row from `results`, keep `totalCount` → `complete is False` in full mode).
  - Swiggy: `test_parses_listing` (`len(jobs) == total`; `external_id` is the digits from `u`; `posted_at == from_ms(d)`); `test_missing_jobs_key_raises_parse_error`.
- [ ] **Step 3: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_smartrecruiters_page.py tests/adapters/test_phonepe.py tests/adapters/test_swiggy.py -v`
  Expected: FAIL.
- [ ] **Step 4: Implement**, and register both adapters.
- [ ] **Step 5: Run the tests to see them pass**, then commit `feat: phonepe and swiggy adapters via smartrecruiters job pages`.

### Task 5: Amazon

**Files:** Create `app/adapters/company/amazon.py`, `tests/adapters/test_amazon.py`, fixtures in `tests/fixtures/amazon/`.

**Interfaces:**
- `amazon` (`name = "amazon"`, `listing_has_details = True`). cfg `{"queries": [{"base_query": "intern"}, {"normalized_country_code[]": "IND"}]}`.
- Request: `GET https://www.amazon.jobs/en/search.json` with the query's params, plus `offset`, `result_limit=100`, `sort=recent`. Answer: `{"error", "hits", "jobs", …}`. A non-null `error`, or a missing `jobs`/`hits` → `ParseError`.
- Paging:
  - Full mode pages each query until `offset >= hits`.
  - Incremental mode reads page 1 of each query.
  - `HITS_CAP = 10000`: a query with `hits >= 10000` can't be read in full, so `complete=False`.
- `reported_total = sum(hits per query) − duplicates`, where a duplicate is a row whose `id_icims` an earlier query already returned (D7). `complete = mode == "full"` and every query was read to `hits` and is under the cap.
- Mapping:
  - `external_id=id_icims`; `title=title.strip()`; `url="https://www.amazon.jobs" + job_path`; `apply_url=url_next_step`.
  - Each `locations[]` entry is a JSON string: `locations` = its `normalizedLocation` values, and `country_codes` = its `countryIso2a` values (fall back to `normalized_location` and `country_codes()` when `locations` is empty).
  - `posted_at` = `posted_date` parsed with `"%B %d, %Y"` as UTC midnight. `employment_type=job_schedule_type`.
  - `description_html = join_sections([(None, description), ("Basic qualifications", basic_qualifications), ("Preferred qualifications", preferred_qualifications)])`.
  - `platform_flags`: `intern` when `is_intern` is truthy and `university` when `university_job` is truthy. Both are null today; this keeps the signal if Amazon fills them.
- `fetch_detail` returns the job unchanged, with no request. Closing relies on the 2-sweep rule.

- [ ] **Step 1: Record fixtures:** `amazon intern_page1 GET "https://www.amazon.jobs/en/search.json?base_query=intern&offset=0&result_limit=25&sort=recent"` and `amazon india_page1 GET "https://www.amazon.jobs/en/search.json?normalized_country_code%5B%5D=IND&offset=0&result_limit=25&sort=recent"`.
- [ ] **Step 2: Write the failing tests:**
  - `test_parses_listing`: per-field mapping for `india_page1.jobs[0]`, including `country_codes == ["IN"]` and `posted_at` from `posted_date`.
  - `test_pages_until_hits`: set `hits = 60` on both fixtures and use `result_limit` 25 through a module constant. Full mode requests offsets `0, 25, 50` per query, and `complete is True`.
  - `test_overlapping_queries_count_duplicates_once`: both queries are served `india_page1` with `hits` equal to its row count. `reported_total == len(res.jobs)`, and `_mismatch(len(res.jobs), res.reported_total)` is False.
  - `test_hits_cap_not_complete`: `hits = 10000` → `complete is False`.
  - `test_incremental_reads_page_one`: one request per query.
  - `test_error_field_raises_parse_error`.
- [ ] **Step 3: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_amazon.py -v`
  Expected: FAIL.
- [ ] **Step 4: Implement** (keep the page size as `PAGE = 100` and let the test patch it), and register.
- [ ] **Step 5: Run the tests to see them pass**, then commit `feat: amazon adapter`.

### Task 6: Apple

**Files:** Create `app/adapters/company/apple.py`, `tests/adapters/test_apple.py`, fixtures in `tests/fixtures/apple/`.

**Interfaces:**
- `apple` (`name = "apple"`). cfg `{"locale": "en-in", "team": "internships-STDNT-INTRN"}`.
- Data: each page embeds `window.__staticRouterHydrationData = JSON.parse("…");`. Decode it as `json.loads(json.loads(<the quoted string>))`. A page without it → `ParseError`.
- Listing: `GET https://jobs.apple.com/{locale}/search?team={team}&page=N` (N from 1, 20 per page). Data in `loaderData.search`: `searchResults`, `totalRecords` (130 on 2026-11-11).
  - Full mode reads `ceil(totalRecords / 20)` pages.
  - Incremental mode reads page 1 with `sort=newest`. While recording, check that `sort=newest` is in `loaderData.search.sort` and puts the largest `postDateInGMT` first. If it doesn't, incremental reads every page; write down which in companies.md.
  - `reported_total=totalRecords`.
- Mapping:
  - `external_id=id` (e.g. `"200691891-3715"`); `title=postingTitle`; `url=f"https://jobs.apple.com/{locale}/details/{id}/{transformedPostingTitle}"`.
  - `locations = [", ".join(p for p in (city, stateProvince, countryName) if p)]` per location; `country_codes(locations)`.
  - `posted_at=postDateInGMT`; `platform_flags={"intern": True}` (the team filter is "Students: Internships").
- Detail: the job page's `loaderData.jobDetails.jobsData`.
  - `description_html = join_sections([(None, text_to_html(jobSummary)), ("Description", text_to_html(description)), ("Responsibilities", text_to_html(responsibilities)), ("Minimum qualifications", text_to_html(minimumQualifications)), ("Preferred qualifications", text_to_html(preferredQualifications))])`.
  - `employment_type=employmentType`; `apply_url=url`.
  - A missing job: use whatever the recorded `missing` page shows (expected: a 404 status or `jobsData` empty) → `GONE`.

- [ ] **Step 1: Record fixtures:** `apple search_p1 GET "https://jobs.apple.com/en-in/search?team=internships-STDNT-INTRN&page=1"`, `apple search_p2 … &page=2`, `apple detail GET "https://jobs.apple.com/en-in/details/{an id from p1}/{its slug}"`, and `apple missing GET "https://jobs.apple.com/en-in/details/000000000-0000/missing"`. All are HTML. jobs.apple.com has no robots.txt: `/robots.txt` redirects to apple.com's 404 page, which counts as "allow all".
- [ ] **Step 2: Write the failing tests:** `test_parses_hydration_listing` (20 jobs from p1, mapped fields, `reported_total == totalRecords`); `test_full_reads_all_pages` (pages `1..ceil(total/20)` requested, with p2 served for the later pages); `test_detail_text_to_html` (`description_html` contains `<h3>Minimum qualifications</h3>`, and no newline sits outside a tag); `test_detail_missing_is_gone`; `test_page_without_hydration_raises_parse_error`.
- [ ] **Step 3: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_apple.py -v`
  Expected: FAIL.
- [ ] **Step 4: Implement** and register.
- [ ] **Step 5: Run the tests to see them pass**, then commit `feat: apple adapter`.

### Task 7: Listing-only JSON adapters — Atlassian, AMD, Capgemini, IBM

Four subtasks (7a–7d), each with the same five steps: record → failing tests → run (FAIL) → implement + register → run (PASS) → commit `feat: <name> adapter`. All four set `listing_has_details = True`. Their `fetch_detail` returns the job unchanged with no request, so closing relies on the 2-sweep rule.

**Interfaces:**
- **7a `atlassian`.** cfg `{}`.
  - Listing: `GET https://www.atlassian.com/endpoint/careers/listings` returns a JSON list of every job (358 on 2026-11-11). robots.txt doesn't disallow `/endpoint` for `*`.
  - Mapping: `external_id=id`; `title`; `url=portalJobPost.portalUrl`; `apply_url=applyUrl`; `locations` (already a list of strings); `country_codes(locations)`; `remote_type="remote"` when every location starts with `"Remote"`.
  - `description_html = join_sections([(None, overview), ("Responsibilities", responsibilities), ("Qualifications", qualifications)])`. `posted_at=None`, because `portalJobPost.updatedDate` is an update time, not a posting time.
  - `reported_total=None`.
  - Tests: `test_parses_listing`; `test_remote_only_locations`; `test_not_a_list_raises_parse_error`.
- **7b `amd`.** cfg `{"intern_category": "Student / Intern / Temp"}`.
  - Full mode: `GET https://careers.amd.com/api/jobs?page=N&limit=100` until `N * 100 >= totalCount` (1,300 jobs). Incremental mode: the same URL plus `categories={intern_category}`, page 1 (37 jobs).
  - Items are `jobs[].data`. Mapping: `external_id=req_id`; `title`; `url=meta_data.canonical_url`; `apply_url`; `locations=[full_location]`; `country_codes = {country_code} ∪ country_codes(locations)`; `posted_at` = `posted_date` parsed with `"%Y-%m-%dT%H:%M:%S%z"`; `employment_type`.
  - `description_html = join_sections([(None, description), ("Responsibilities", responsibilities), ("Qualifications", qualifications)])`.
  - `platform_flags={"intern": True}` when any `categories[].name == intern_category`.
  - `reported_total=totalCount`. The `crawl-delay: 5` comes from Task 2.
  - Fixtures: `amd interns GET "https://careers.amd.com/api/jobs?categories=Student%20%2F%20Intern%20%2F%20Temp&page=1&limit=25"`, `amd all_p1 GET "https://careers.amd.com/api/jobs?page=1&limit=25"`.
  - Tests: `test_parses_listing`; `test_intern_category_sets_flag`; `test_incremental_filters_category` (the request has `categories`); `test_full_pages_until_total`.
- **7c `capgemini`.** cfg `{"country_code": "en-in"}`.
  - Listing: `GET https://cg-jobstream-api.azurewebsites.net/api/job-search?country_code={country_code}&page=N&size=100` → `{"count", "data", "total", …}` (705 India jobs). While recording, check whether `page` starts at 1 and whether `data` comes newest-first by `indexed_at`. Incremental mode reads page 1 only if it does; otherwise it reads every page (D10). Write down which in companies.md.
  - Mapping: `external_id=id`; `title`; `url=apply_job_url`; `locations=[p.strip() for p in location.split(",")]`; `country_codes = {"IN"} ∪ country_codes(locations)` (from the cfg's `en-in` suffix, uppercased); `employment_type=contract_type`; `description_html=description`.
  - `platform_flags={"intern": True}` when `experience_level` or `contract_type` matches `(?i)\bintern|student`. `reported_total=total`.
  - Tests: `test_parses_listing`; `test_full_pages_until_total`; `test_missing_data_raises_parse_error`.
- **7d `ibm`.** cfg `{}`.
  - Listing: `POST https://www-api.ibm.com/search/api/v2` with this body (`FROM` steps by 100; `SIZE = 100`):
    ```json
    {"appId":"careers","scopes":["careers2"],"query":{"bool":{"must":[]}},
     "post_filter":{"bool":{"must":[{"term":{"field_keyword_18":"Internship"}}]}},
     "size":100,"from":FROM,"sort":[{"dcdate":"desc"}],"lang":"zz","localeSelector":{},
     "sm":{"query":"","lang":"zz"},
     "_source":["_id","title","url","description","dcdate","field_keyword_08",
                "field_keyword_17","field_keyword_18","field_keyword_19"]}
    ```
    The answer is `hits.total.value` (236 on 2026-11-11) and `hits.hits[]._source`. Full mode pages until `from >= total`; incremental mode reads the first page.
  - Mapping: `external_id` = the `jobId` query value of `url`; `title`; `url`; `locations=[field_keyword_19]` (e.g. `"Singapore, SG"`); `country_codes` = the text after the last `", "` when pycountry knows it as alpha-2, plus `country_codes(locations)`; `remote_type` from `field_keyword_17` (`Hybrid`→hybrid, `Remote`→remote, `On-site`/`Onsite`→onsite); `posted_at=dcdate` (UTC midnight); `description_html=text_to_html(description)` (D6, the snippet only); `platform_flags={"intern": True}`.
  - `reported_total=hits.total.value`.
  - Fixture: `ibm page1 POST https://www-api.ibm.com/search/api/v2 --json '<the body with size 25, from 0>'`.
  - Tests: `test_parses_listing`; `test_country_from_suffix`; `test_full_pages_until_total` (set total to 60 with `SIZE` patched to 25 → `from` values `0, 25, 50`); `test_ibm_never_requests_careers_site` (respx route for `careers.ibm.com` asserted not called after `list_jobs` and `fetch_detail`).

### Task 8: Zerodha (empty-allowed source)

**Files:** Create `app/adapters/company/zerodha.py`, `tests/adapters/test_zerodha.py`, fixture `tests/fixtures/zerodha/empty.json`.

**Interfaces:**
- `zerodha` (`name = "zerodha"`, `listing_has_details = True`). cfg `{"allow_empty": true}`.
- Listing: `GET https://careers.zerodha.com/api/jobs` → `{"count", "data", "success"}`.
  - `success` not true, or `data` not a list → `ParseError`.
  - `reported_total=count`; `complete = mode == "full"`.
- Item field names come from the site's script (`careers.zerodha.com/assets/index-*.js`, the code after `fetch("/api/jobs")`). On 2026-11-11 the script reads `location` and `description` from each job. The implementer reads the job-card markup in that script for the ID and title fields and records them in a module docstring. A row without an ID uses the title (lowercased, spaces → `-`) as `external_id`.
- `url = "https://careers.zerodha.com/#job-openings"` (there are no per-job pages); `description_html=description`.
- `fetch_detail` re-reads `/api/jobs` and returns `GONE` when the ID is no longer listed, so the tracked re-check closes Liked/Applied jobs. Otherwise it returns the listed job.

- [ ] **Step 1: Record** `zerodha empty GET https://careers.zerodha.com/api/jobs` (expected `{"count":0,"data":[],"success":true}`). If jobs are listed by then, also record `zerodha page` and add `test_parses_listing` in Step 2.
- [ ] **Step 2: Write the failing tests:** `test_empty_answer_is_healthy` (`jobs == []`, `complete is True` in full mode, `evaluate(res, "full", {"allow_empty": True}) == []`); `test_unsuccessful_raises_parse_error` (`success` set to false); `test_detail_gone_when_not_listed` (`fetch_detail` on any job against the empty fixture → `GONE`).
- [ ] **Step 3: Run them to see them fail**
  Run: `uv run pytest tests/adapters/test_zerodha.py -v`
  Expected: FAIL.
- [ ] **Step 4: Implement** and register.
- [ ] **Step 5: Run the tests to see them pass**, then commit `feat: zerodha adapter (empty allowed)`.

### Task 9: Registry, dashboard labels, docs and the live check

**Files:** Modify `config/sources.yaml`, `tests/core/test_registry.py:58-59`, `web/src/pages/Sources.tsx`, `web/src/components/AddCompanyDialog.tsx` (+ its test), `docs/companies.md`, `docs/DESIGN.md` (§1, §2, §12). Create `docs/R2b-notes.md`.

**Interfaces:**
- `sources.yaml`:
  - Add one source per company: `paytm`, `meesho`, `cred` (adapter `lever`, `site` = the slug); `razorpay` (`board: razorpaysoftwareprivatelimited`), `groww`, `inmobi` (adapter `greenhouse`); `amazon`, `apple`, `atlassian`, `amd`, `ibm`, `capgemini`, `phonepe`, `swiggy` with the cfg values from Tasks 4–7; `zerodha` with `{allow_empty: true}`.
  - Add `meta` and `goldman` as `supported: false` with the D1/D2 reasons.
  - Update the header's config-key comment for each new adapter.
- `Sources.tsx` label map: `lever: "Lever"`, `greenhouse: "Greenhouse"`, and `"<Company> (own site)"` for the nine company adapters.
- `describe()` in `AddCompanyDialog.tsx`: `lever` → `` `Lever · ${c.site}` ``; `greenhouse` → `` `Greenhouse · ${c.board}` ``. The name pre-fill uses `key_hint` for both.

- [ ] **Step 1: Write the failing tests**
  - `test_shipped_registry_valid` now expects **43** supported companies and **14** unsupported, each with a reason.
  - Add a `describe()` test for one Lever and one Greenhouse `Detected`.
- [ ] **Step 2: Run them to see them fail**
  Run: `uv run pytest tests/core/test_registry.py -v && (cd web && npm run check)`
  Expected: FAIL (28 ≠ 43; the describe test fails).
- [ ] **Step 3: Fill in the YAML and the labels.**
- [ ] **Step 4: Run every check, then the live check**
  - Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && (cd web && npm run check)`. Expected: all pass.
  - Run `uv run python -m app.cli live-check --source <key> --mode full` for each of the 15 new sources. Expected: `OK` for every source (Zerodha OK with 0 jobs). A failure is fixed in its adapter task's file, and its fixture re-recorded if the site changed.
  - Then run `uv run python -m app.cli live-check --mode incremental` once for all sources. Expected: every source OK, the 28 R1 sources included.
- [ ] **Step 5: Update the docs**
  - `companies.md` R2 table: the endpoints, filters and checks recorded in Tasks 3–8 (Swiggy `r`/`h`, Apple and Capgemini order, the SmartRecruiters "removed" answer, AMD crawl-delay, Amazon's ignored filters). Move Meta and Goldman to "Not supported" with their reasons. Add a note that SmartRecruiters job pages are read as JSON, which may let Freshworks, Bosch and ServiceNow come back later.
  - `DESIGN.md`: 66 → 64 companies (§1); 12 → 14 unsupported (§2); §12 counts R2 43, R3 57, R4 64.
  - `R2b-notes.md`, in R2-notes' format: status table (tests, live check per source with job counts), decisions made during the build, what's not checked yet (Zerodha's parser has no non-empty fixture), and anything left for later.
  - Commit: `feat: register R2b companies; docs and live-check results`.
