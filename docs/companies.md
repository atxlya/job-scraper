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

## R2 — +17 (45 total)

| Company | Adapter | Source details | Internship filter |
|---|---|---|---|
| Paytm | Lever | `api.lever.co/v0/postings/paytm?mode=json` | `commitment=Intern` |
| Meesho | Lever | `api.lever.co/v0/postings/meesho?mode=json` | commitment |
| CRED | Lever | `api.lever.co/v0/postings/cred?mode=json` | commitment |
| Razorpay | Greenhouse | `boards-api.greenhouse.io/v1/boards/razorpaysoftwareprivatelimited/jobs` | title |
| Groww | Greenhouse | `boards-api.greenhouse.io/v1/boards/groww/jobs` | title |
| InMobi | Greenhouse | `boards-api.greenhouse.io/v1/boards/inmobi/jobs` | title (not yet confirmed that the careers page uses this board) |
| Amazon | `company/amazon` | `amazon.jobs/en/search.json?normalized_country_code[]=…&offset=&result_limit=` | fields `is_intern`, `university_job` |
| Apple | `company/apple` | search pages embed results as JSON | `team=internships-STDNT-INTRN` |
| Meta | `company/meta` | sitemap `metacareers.com/jobs/sitemap.xml` + JSON-LD on job pages | `employmentType` / title. robots disallows `/ajax/` |
| Atlassian | `company/atlassian` | `atlassian.com/endpoint/careers/listings` (all jobs in one response) | title |
| AMD | `company/amd` (iCIMS Jibe) | `careers.amd.com/api/jobs?keywords=&page=&limit=` | keywords |
| IBM | `company/ibm` | `POST www-api.ibm.com/search/api/v2` (`appId:"careers"`, `scopes:["careers2"]`) | `field_keyword_18`=Internship. careers.ibm.com itself has an AWS WAF challenge; don't touch it |
| Capgemini | `company/capgemini` | `cg-jobstream-api.azurewebsites.net/api/job-search?country_code=en-in&page=&size=` | `experience_level` |
| PhonePe | `company/phonepe` | `phonepe.com/apollo/job-postings/latest.json` | `type=Intern`; keep `status=PUBLIC` |
| Zerodha | `company/zerodha` | `careers.zerodha.com/api/jobs` | keyword |
| Swiggy | `company/swiggy` | `careers.swiggy.in/api/jobs.json` (own endpoint; **not** the SmartRecruiters API) | title |
| Goldman Sachs | `company/goldman` | `POST api-higher.gs.com/gateway/api/v1/graphql`, `roleSearch` | `experiences:["EARLY_CAREER"]`. Campus internship portal not yet found; higher.gs.com robots allows only `/roles/` |

## R3 — +14 (59 total)

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

## R4 — +7 (66 total), Playwright

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

Possible later revisit: SmartRecruiters' public job pages (`jobs.smartrecruiters.com/{Company}`) had no robots.txt rules on 2026-11-10. If they can be parsed reliably, Freshworks, Bosch and ServiceNow could move back to automated.

Note: `companies.txt` line 58 "vPayPal" is PayPal.
