# Company coverage

Findings from checking each careers site with live requests on **2026-11-10**. Job counts are what the site showed that day; many India internship counts were 0 and look seasonal. "WD" means Workday's public JSON search endpoint:

```
POST https://{host}/wday/cxs/{tenant}/{site}/jobs
Content-Type: application/json   Accept: application/json
{"appliedFacets":{}, "limit":20, "offset":0, "searchText":""}
```

Filter Workday internships by facet ID (`workerSubType` / `jobFamilyGroup`) from the response's `facets`, not by `searchText`, which matches loosely.

Eightfold sites use `GET /api/pcsx/search?domain={d}&query=&location=&start=N` (10 per page) and `GET /api/pcsx/position_details?position_id={id}&domain={d}`. The older `/api/apply/v2/jobs` now returns 403 on most of them (HSBC still works).

Oracle HCM sites use `GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber={site},limit=N,offset=N`. Its `keyword` search is unreliable ("intern" also matches "internal"), so filter titles or use category/flex facets.

---

## R1 — 28 companies

### Original three
| Company | Adapter | Source details | Internship filter | robots / notes |
|---|---|---|---|---|
| Google | `company/google` | `/about/careers/applications/jobs/results/?target_level=INTERN_AND_APPRENTICE&location=…&sort_by=date` — job data is JSON in `AF_initDataCallback({key:'ds:1'…})`, as positional arrays | `target_level=INTERN_AND_APPRENTICE` (≈90 jobs), `EARLY` (≈300) | robots disallows `&page=`, so **page 1 only**, with narrow per-country queries. Closed job: HTTP 200 with empty `ds:0`. Risk: medium-high (undocumented arrays) |
| NVIDIA | Eightfold (`jobs.nvidia.com`, domain `nvidia.com`) | `/api/pcsx/search`, `/api/pcsx/position_details`; sitemap `/careers/sitemap.xml` | `filter_job_category=univ employment` (≈220) | robots allows `/careers`, `/api/pcsx`. Applications go to Workday `nvidia.wd5` / `NVIDIAExternalCareerSite` (fallback). Closed: JSON 404 |
| Barclays | `company/barclays` (Radancy) | `GET search.jobs.barclays/search-jobs/results?CurrentPage=N&RecordsPerPage=100&Keywords=&SearchType=5&OrganizationIds=13015&…` returns JSON `{results: html}`; detail page `/job/{city}/{slug}/13015/{id}` has JSON-LD JobPosting | Internships facet (FacetType=1, id 8249920) | robots has no rules. Location needs facet IDs (India = 1269750). Fallback: Workday `barclays.wd3` / `External_Career_Site_Barclays`. Closed: 404 |

### Workday (14)
| Company | Host / tenant / site | Internship filter | Notes |
|---|---|---|---|
| VMware (Broadcom) | `broadcom.wd1` / `broadcom` / `External_Career` | none (only "Regular") | ≈387 jobs; India locations start with `IND-` |
| Accenture | `accenture.wd103` / `accenture` / `AccentureCareers` | `searchText` "intern" | `total` caps at 2000, so split queries by facet. accenture.com's own search is disallowed; Workday is allowed |
| PwC | `pwc.wd3` / `pwc` / `Global_Experienced_Careers` + `Global_Campus_Careers` | `workerSubType` Intern / Intern (Trainee) | pwc.in returns 403 (Akamai) |
| BrowserStack | `browserstack.wd3` / `browserstack` / `External` | none | ≈31 jobs |
| Philips | `philips.wd3` / `philips` / `jobs-and-careers` | `jobFamilyGroup` "EA Trainees, Interns and Apprentices" (≈107) | Phenom front end |
| Wells Fargo | `wf.wd1` / `wf` / `WellsFargoJobs` | `workerSubType` "Intern (Fixed Term)" | front site behind Cloudflare; Workday API open |
| Deutsche Bank | `db.wd3` / `db` / `DBWebSite` | `workerSubType` "Q (Interns / Practical Work Exp.)" (≈39) | ≈297 India |
| Mastercard | `mastercard.wd1` / `mastercard` / `CorporateCareers` + `Campus` | `workerSubType` Intern | two sources |
| Visa | `visa.wd5` / `visa` / `Visa` + `Visa_Early_Careers` | `jobFamily` Intern | two sources |
| Samsung R&D India | `sec.wd3` / `sec` / `Samsung_Careers` | `workerSubType` Intern(Empl.); `hiringCompany` = SRI-B | |
| Salesforce | `salesforce.wd12` / `salesforce` / `External_Career_Site` + `Futureforce_Internships` | `workerSubType` "Intern (Fixed Term)" | two sources |
| Adobe | `adobe.wd5` / `adobe` / `external_experienced` | `workerSubType` Intern; `jobFamilyGroup` University | `external_university` returns 403; robots allows only `external_experienced` |
| Cisco | `cisco.wd5` / `cisco` / `Cisco_Careers` | `jobFamilyGroup` "Apprentice & Intern" | Phenom disallows only `*/apply` |
| Intel | `intel.wd1` / `intel` / `External` | `workerSubType` "Student / Intern" (≈96) | jobs.intel.com redirects to a 404 page; use Workday directly |

### Eightfold (5 more)
| Company | Host / domain | Notes |
|---|---|---|
| Microsoft | `apply.careers.microsoft.com` / `microsoft.com` | `employment_type` filter has "internship" |
| Qualcomm | `careers.qualcomm.com` / `qualcomm.com` | |
| Morgan Stanley | `morganstanley.eightfold.ai` / `morganstanley.com` | |
| PayPal | `paypal.eightfold.ai` / `paypal.com` | careers.pypl.com is behind Cloudflare; the Eightfold host is open |
| HSBC | `portal.careers.hsbc.com` / `hsbc.com` | `/api/apply/v2/jobs?…&query=intern&location=India` works |

### Oracle HCM (6)
| Company | Host / site | Internship filter |
|---|---|---|
| American Express | `egug.fa.us2.oraclecloud.com` / `CX_1` | filter titles |
| JPMorgan Chase | `jpmc.fa.oraclecloud.com` / `CX_1001` | filter titles (≈7,071 jobs) |
| Oracle | `eeho.fa.us2.oraclecloud.com` / `CX_45001` | flex facet "Student/Intern" |
| Dell | `enterpriseplatform.dell.com` / `CX_1001` | category "Undergraduate Intern" |
| KPMG India | `ejgk.fa.em2.oraclecloud.com` / `CX_3` (+ `CX_3001`) | keyword |
| Honeywell | `ibqbjb.fa.ocs.oraclecloud.com` / `CX_1` | keyword (loose) |

---

## R2 — +15 (43 total)

Built in R2b ([plan](superpowers/plans/2026-11-11-r2b-adapters.md), [notes](R2b-notes.md)). Every endpoint was re-checked live on **2026-11-11**. Meta and Goldman Sachs moved to [Not supported](#not-supported).

| Company | Adapter | Source details | Internship filter / notes |
|---|---|---|---|
| Paytm | Lever | `api.lever.co/v0/postings/paytm?mode=json`: one list, full descriptions (≈3 MB) | `categories.commitment` "Intern" → intern flag. Detail `/v0/postings/paytm/{id}`, 404 when gone |
| Meesho | Lever | `…/postings/meesho?mode=json` | title only (no "Intern" commitment today) |
| CRED | Lever | `…/postings/cred?mode=json` | title only |
| Razorpay | Greenhouse | `boards-api.greenhouse.io/v1/boards/razorpaysoftwareprivatelimited/jobs` | title. `content=true` (HTML-escaped) only in the full sweep |
| Groww | Greenhouse | `…/boards/groww/jobs` (job links are on `job-boards.eu.greenhouse.io`; the API host is the same) | title |
| InMobi | Greenhouse | `…/boards/inmobi/jobs` (79 jobs, active) | title; `metadata` "Employment Type" |
| Amazon | `company/amazon` | `amazon.jobs/en/search.json?…&result_limit=100&sort=recent`, two queries: `base_query=intern` (≈477) and `normalized_country_code[]=IND` (≈2,080) | Amazon ignores `job_type[]`, `business_category[]` and `team[]`, and `is_intern` / `university_job` are always null, so titles decide. `hits` caps at 10,000 |
| Apple | `company/apple` | `jobs.apple.com/en-in/search?team=internships-STDNT-INTRN&page=N` (20 per page, ≈130); data in `window.__staticRouterHydrationData = JSON.parse("…")` | every result is an internship. `sort=newest` is newest-first. Job page has the same hydration data; a removed job answers 200 with no `jobDetails`. No robots.txt |
| Atlassian | `company/atlassian` | `atlassian.com/endpoint/careers/listings`: every job (≈358) with full text | title. Links go to the iCIMS job page (`portalJobPost.portalUrl`) |
| AMD | `company/amd` (iCIMS Jibe) | `careers.amd.com/api/jobs?page=N&limit=100` (≈1,300) | `categories=Student / Intern / Temp` (≈37). robots.txt sets `crawl-delay: 5`, which the client honours |
| IBM | `company/ibm` | `POST www-api.ibm.com/search/api/v2` (`appId:"careers"`, `scopes:["careers2"]`, `post_filter` `field_keyword_18`=Internship, sorted by `dcdate`) (≈236) | search snippet only: careers.ibm.com has an AWS WAF challenge and is never fetched |
| Capgemini | `company/capgemini` | `cg-jobstream-api.azurewebsites.net/api/job-search?country_code=en-in&page=N&size=100` (≈705) | pages start at 1 and aren't newest-first, so every run reads every page. `experience_level` today is only Experienced Professionals / Executives |
| PhonePe | `company/phonepe` | `phonepe.com/apollo/job-postings/latest.json` (955 rows) | keep `status=PUBLIC` (≈153); `type=Intern`. Descriptions from the SmartRecruiters job page (below) |
| Zerodha | `company/zerodha` | `careers.zerodha.com/api/jobs` → `{count, data, success}`; fields `name`, `job_title`, `location`, `location_type`, `description` (from the site's script) | **0 openings on 2026-11-11**; the source has `allow_empty: true` |
| Swiggy | `company/swiggy` | `careers.swiggy.in/api/jobs.json` (≈194): keys `t` title, `l` location, `e` type, `d` epoch ms, `u` link, `r`=1 Remote, `h`=1 Hybrid (from the site's script) | title. Descriptions from the SmartRecruiters job page |

**SmartRecruiters job pages.** `jobs.smartrecruiters.com/{Company}/{id}-{slug}` with `Accept: application/json` returns the posting as JSON (`jobTitle`, `content.sections`, `postedDate`, `employmentType`). That host has no robots.txt; a removed posting answers 404 (HTML). The API host `api.smartrecruiters.com` stays off limits.

## R3 — +14 (57 total)

| Company | Adapter | Source details |
|---|---|---|
| Wipro | SuccessFactors sitemap | `careers.wipro.com/sitemap.xml` + schema.org microdata on job pages (`/services/` is disallowed) |
| HCLTech | SuccessFactors sitemap | `careers.hcltech.com/sitemap.xml` |
| EY | SuccessFactors sitemap | `careers.ey.com` sitemap / HTML `/search/` |
| Deloitte India | SuccessFactors sitemap | `southasiacareers.deloitte.com` sitemap |
| Siemens | RSS (Avature) | `jobs.siemens.com/en_US/externaljobs/SearchJobs/feed/` |
| Zoho | RSS | `careers.zohocorp.com/jobs/Careers/rss` |
| Tata Elxsi | notice page (HTML list) | `tataelxsi.com/careers/job-openings?page=1..N` |
| DRDO | notice page | `drdo.gov.in/drdo/en/offerings/vacancies` (+ `/archive`) |
| ISRO | notice page | `isro.gov.in/Careers.html` (compare the set of `*Recruitment*.html` links) |
| CDAC | notice page | `cdac.in/index.aspx?id=current_jobs` + PDFs (careers.cdac.in has a broken TLS chain) |
| BARC | notice page | `barc.gov.in/careers/recruitment.html` + PDFs |
| Cognizant | partial (sitemap) | `careers.cognizant.com` sitemap (≈3.3k jobs); job pages behind Cloudflare, so title + link only |
| Uber | partial (sitemap) | `jobs.uber.com/en/jobs/sitemap.xml`; job pages return 403 |
| SAP | partial (sitemap) | `jobs.sap.com/en/jobs/sitemap.xml`; pages behind Cloudflare; robots disallows `?q=` |

## R4 — +7 (64 total), Playwright

| Company | Site | Platform |
|---|---|---|
| Tech Mahindra | `careers.techmahindra.com/CurrentOpportunity.aspx` | custom ASP.NET |
| LTIMindtree (LTM) | `ltm.com/careers` → `ltm.ripplehire.com` | RippleHire |
| Myntra | `jobs.myntra.com/home` | Spire2Grow (Flutter) |
| ShareChat | `sharechat.mynexthire.com/employer/jobs` | MyNextHire |
| Urban Company | `careers.urbancompany.com/jobs` | custom React |
| Jio Platforms | `careers.jio.com/frmJobCategories.aspx` (+ `frmStudent_Campus.aspx`) | ASP.NET WebForms |
| Reliance (Digital) | `careers.ril.com/rilcareers/frmcareersN.aspx` | ASP.NET WebForms |

Before building each of these, re-check robots.txt and whether the site blocks automated access. If it does, move the company to the list below.

---

## Not supported

These are not built. Check them manually.

| Company | Why |
|---|---|
| TCS | Akamai bot protection (403) |
| Infosys | Akamai bot protection (403, including robots.txt) |
| BharatPe | Darwinbox API behind Cloudflare (403) |
| Unacademy | Darwinbox API behind Cloudflare (403) |
| Airtel Digital | Darwinbox behind Akamai |
| Flipkart | TurboHire robots.txt disallows every bot except Googlebot |
| Ola | TurboHire robots.txt disallows every bot except Googlebot |
| Ola Electric | TurboHire robots.txt disallows every bot except Googlebot |
| Zomato (Eternal) | No job board; the company asks for referrals or email |
| Freshworks | SmartRecruiters API robots.txt allows only LinkedInBot |
| Bosch | SmartRecruiters API robots.txt allows only LinkedInBot |
| ServiceNow | SmartRecruiters API robots.txt allows only LinkedInBot |
| Meta | metacareers.com robots.txt opens with a notice that automated collection is prohibited without written permission (its rules alone would allow job pages) |
| Goldman Sachs | higher.gs.com's `roleSearch` API works, but has no internships (`EARLY_CAREER` = 6 call-centre and analyst roles on 2026-11-11); the campus internship portal hasn't been found |

Possible later revisit: SmartRecruiters' public job pages are now read as JSON for PhonePe and Swiggy (see R2). A company's job list on `jobs.smartrecruiters.com/{Company}` might work the same way, which could move Freshworks, Bosch and ServiceNow back to automated.

Note: `companies.txt` line 58 "vPayPal" is PayPal.
