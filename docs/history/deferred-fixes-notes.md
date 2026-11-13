# Deferred fixes: the "Left for later" items from R1–R4

Branch `fix-deferred`, 2026-11-11. Every code item in the "Left for later" sections of the [R2](R2-notes.md), [R2b](R2b-notes.md), [R3](R3-notes.md) and [R4](R4-notes.md) notes: 46 in all. 41 were fixed here and 5 had already been fixed by the R3 review pass (their notes were out of date). Each fix has a test written to fail first, except the items that only asked for missing tests.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 615 passing (was 534) |
| Web tests (`cd web && npm run check`) | 47 passing (was 40); type-check clean; build OK |
| Live check, incremental, every source | 0 failed of 65 |
| Live check, full mode, the 12 sources whose code changed | All OK: jio-tech 246/246, reliance 44, techmahindra 504, zoho 9, tataelxsi 83, cdac 30, barc 5, drdo 9, isro 17, ibm-interns 237/237, myntra 51/51, sharechat 11 |
| Recorded notice titles (82) | Same internship/skip decision as before the skip-word change |
| Independent review of the branch | No critical findings; 3 important and the clear minors fixed (last section) |

## What changed

**Scraping runs**
- The daily re-check of liked and applied jobs carries on past a job that fails. The run is "partial", with the failures in its error. If every job fails, the run fails.
- A job page that answers 200 with something other than JSON skips that job, not the whole source. Any other error in a job page (an adapter bug) still fails the run. A listing run where every job page fails is marked "partial".
- Myntra's workspace id, Zerodha's list and Zoho's feed are each read once a run, not once per job.

**R4 sites**
- Jio, Reliance and Tech Mahindra never follow a redirect on their pages; a redirect (to `/error.aspx`) is a parse error.
- Tech Mahindra checks that "Last" really reached a later page.
- Jio and Reliance fail the run if the page count changes mid-walk.
- ShareChat counts a 417 as "gone" only with its "not accepting applications" message.

**R3 sites**
- SuccessFactors: a redirect with no `Location` is a parse error.
- RSS: an item without a title or link is skipped and the sweep isn't counted as complete. A job missing from such a feed isn't called gone.
- Tata Elxsi: only real pager links count, and a job link without a path is a parse error.
- Notices:
  - DRDO's `http://` links, PDF links included, are upgraded only on DRDO's own host.
  - CDAC application-form and annexure links are no longer separate notices.
  - BARC handles a header row outside `<thead>` and a "no vacancies" row.
  - An ISRO link with no text gets a title from its page name.
- Cognizant/SAP `job_url` and the notice `site` are checked when `sources.yaml` loads, so a typo stops start-up with the source named.
- "Result" and "selected" skip a notice only next to a process word ("written examination result", "Result –", "JRF Results", "candidates selected", "merit list"). A real opening that mentions "selected research projects" or "results analysis" is no longer dropped.

**R2b sites**
- SmartRecruiters ids come only from `https://jobs.smartrecruiters.com` links.
- Apple's page data is matched as a whole string, so a `");` inside a title can't cut it short.
- `allow_empty` keeps only drops to zero quiet; a drop from 40 to 3 still warns.
- Lever adds no heading for a list with no items.
- IBM jobs (search summaries) are no longer sent to Gemini. Platform flags a source starts sending now reach jobs stored earlier, so IBM's stored jobs stop being queued on their next run.

**Fetching**
- A robots.txt behind more than 5 redirects means nothing is fetched from that host.
- `record_fixture.py --no-follow` works for POSTs, and XML trimming keeps the root's namespace.

**Dashboard and login**
- Every `/api` path except `/api/login` needs a valid session, so a route added without the login check is still locked.
- The API docs moved to `/api/docs` and `/api/openapi.json`, behind login.
- A new dashboard password ends every existing session. "Everywhere" in the header (with a confirm) logs out every device. *Everyone is logged out once when this is deployed.*
- Add company: the same careers site under a second name, or a second click while the first is testing, answers "already added" instead of saving twice or erroring.
- Description links open in a new tab, and relative links point at the posting's site.
- Fetching a missing description gives up after 30 s.
- The eligibility box says why a notice, a title-only job or an IBM summary isn't checked.
- Filter counts are done in SQL. The counts are the same, and they take about 100 ms at 40,000 jobs (145–195 ms before).

**Operations**
- `docker compose up` indexes only jobs missing from search (`reindex --missing-only`). The [RUNBOOK](../RUNBOOK.md) shows the full rebuild for updates that change the search or degree rules.

## Already fixed before this branch

These were fixed by the R3 review pass (`613fd31`); only the notes were stale:
- the SuccessFactors and RSS dead `if False` expressions;
- the SuccessFactors second-hop redirect to `/errorpage/`;
- Tata Elxsi treating any redirect as gone;
- redirects being followed without a robots.txt check. Every hop goes through the robots and pacing check.

## Decisions made while fixing

- **Narrower notice skip words.** *Cost if wrong:* a result notice worded unlike the tested forms becomes an alert. It's one unwanted message, and the title shows what it is.
- **Locked by default.** An unknown `/api` path answers 401 until you log in, then 404.
- **No database migration for IBM.** Instead, the next IBM run adds the "snippet" flag to stored jobs and stops their Gemini requests.
- **The CDAC rule matches link text** (application form, interview application, annexure, proforma, format). *Cost if wrong:* a real advert titled with one of those words under a heading is dropped.

## Still not done

These need something code alone can't give, or are limits of the sites themselves:
- **Waiting on real data:**
  - a real Zerodha job, to record and test;
  - a really expired PhonePe or Swiggy posting;
  - what a removed job looks like on LTIMindtree, Jio, Reliance and Tech Mahindra.
- **Limits of the sites:**
  - IBM gives summaries only;
  - Tech Mahindra has no job pages;
  - Wipro and HCLTech can only be listed from their sitemaps;
  - Cognizant and SAP give slug titles only;
  - ShareChat links go to the careers page;
  - Paytm and Atlassian have large lists.
- **Not tried:** SmartRecruiters company pages for Freshworks, Bosch and ServiceNow; Jio's non-tech categories; careers.ltm.com.
- **From the review (minor):**
  - An RSS feed with a permanently broken item stops closing jobs on that source, and only the log says why.
  - Each logged-in request reads the session epoch from SQLite twice.
- **R1 items:** the 555 MB image, `google-genai`'s import warning.
