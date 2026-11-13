# Companies we could add

Checked 2026-11-13. Each candidate's careers board was read once through the project's own adapters and polite client, the same path the dashboard's **Add company** form uses (robots.txt checked, one request every 2.5 s per host). Nothing was added to `config/sources.yaml`.

Left out because they're already in the registry: CRED, Mastercard, Wells Fargo, Philips, VMware/Broadcom (`broadcom`), Meesho, Groww, Razorpay, Samsung R&D. Left out because they're already marked unsupported: Freshworks, Bosch, ServiceNow, Flipkart, Infosys, TCS, Zomato.

**How to read the counts:**
- For Workday and Eightfold, this was the quick (incremental) read, so "Jobs read" is only the first pages. "Site total" is the whole board, and the India and intern counts are for the jobs read only.
- For Greenhouse and Lever, the whole board was read.
- "Intern-like" counts titles containing intern, internship, trainee, co-op or apprentice.

## Work today: add with the Add company form

### Worth adding first (India jobs and internships)

| Company | Platform | Board URL to paste | Jobs read / site total | India | Intern-like |
|---|---|---|---|---|---|
| Databricks | Greenhouse | `https://boards.greenhouse.io/databricks` | 907 / 907 | 85 | 12 |
| Stripe | Greenhouse | `https://boards.greenhouse.io/stripe` | 788 / 788 | 43 | 21 |
| Coinbase | Greenhouse | `https://boards.greenhouse.io/coinbase` | 270 / 270 | 10 | 26 |
| Rubrik | Greenhouse | `https://boards.greenhouse.io/rubrik` | 181 / 181 | 35 | 8 |
| MongoDB | Greenhouse | `https://boards.greenhouse.io/mongodb` | 386 / 386 | 73 | 3 |
| Datadog | Greenhouse | `https://boards.greenhouse.io/datadog` | 385 / 385 | 9 | 6 |
| HPE | Workday | `https://hpe.wd5.myworkdayjobs.com/Jobsathpe` | 60 / 1,789 | 6 | 6 |
| Analog Devices | Workday | `https://analogdevices.wd1.myworkdayjobs.com/External` | 60 / 770 | 2 | 14 |
| Micron | Workday | `https://micron.wd1.myworkdayjobs.com/External` | 60 / 2,895 | 6 | 4 |
| State Street | Workday | `https://statestreet.wd1.myworkdayjobs.com/Global` | 60 / 1,197 | 12 | 1 |
| Autodesk | Workday | `https://autodesk.wd1.myworkdayjobs.com/Ext` | 4 / 4 | 1 | 1 |

Autodesk's board showed only 4 jobs. Its main listing may be on another Workday site, so look at it again before adding.

### They work, but less useful now

These boards had no India jobs or no internships in what was read:

| Company | Platform | Board URL | Jobs read / site total | India | Intern-like |
|---|---|---|---|---|---|
| Palantir | Lever | `https://jobs.lever.co/palantir` | 301 / — | 0 | 48 |
| Cloudflare | Greenhouse | `https://boards.greenhouse.io/cloudflare` | 479 / 479 | 0 | 7 |
| Zeta | Lever | `https://jobs.lever.co/zeta` | 30 / — | 25 | 0 |
| Target | Workday | `https://target.wd5.myworkdayjobs.com/targetcareers` | 60 / 2,000 | 7 | 0 |
| Vodafone (VOIS) | Eightfold | `https://vodafone.eightfold.ai/careers` | 30 / 1,227 | 2 | 0 |
| Fidelity | Workday | `https://fmr.wd1.myworkdayjobs.com/FidelityCareers` | 60 / 885 | 0 | 0 |
| Thomson Reuters | Workday | `https://thomsonreuters.wd5.myworkdayjobs.com/External_Career_Site` | 35 / 538 | 0 | 0 |
| Spotify | Lever | `https://jobs.lever.co/spotify` | 86 / — | 1 | 0 |
| Starbucks | Eightfold | `https://starbucks.eightfold.ai/careers` | 30 / 21,714 | 1 | 0 |

**Notes on these:**
- **Zeta and Target:** they have many India jobs but no internships right now. They're worth adding if you expect intern postings later.
- **Starbucks:** almost all of its 21,714 jobs are store roles, so a full sweep would do a lot of work for little.
- **Accenture-sized boards:** Workday caps its reported total at 2,000 (DESIGN §3). Target shows exactly 2,000, so it is probably capped. The full sweep would then mark the run "partial" until the query is split, as was done for Accenture.

## Didn't work

| Company | What happened | What it means |
|---|---|---|
| Walmart | `walmart.wd5…/WalmartExternal` answered 422 | Walmart uses Workday, but that site name is wrong. Find the real board URL from an Apply link on careers.walmart.com |
| Western Digital | `wdc.wd1…` answered 422 for both site names tried | Same: the real Workday site name is unknown |
| NetApp | `netapp.wd1…/NetAppCareers` answered 422 | Probably not Workday. Third-party guides say SuccessFactors or Radancy |
| Postman | No Greenhouse board named `postman` (404) | Its jobs are elsewhere; not checked further |
| Chevron | No Eightfold site at `chevron.eightfold.ai` (404) | Not on Eightfold under that name |
| Bayer | `bayer.eightfold.ai` answered 403 to the search | Refused: treat it as blocked (DESIGN §2: no getting around bot protection) |

## How to add one

1. Open the dashboard, click **Add company**, enter the name and paste the board URL from the tables above. It's saved only if a test fetch returns real jobs.
2. Or add it to `config/sources.yaml`, then check it and restart the worker:

```bash
uv run python -m app.cli live-check --source <key> --mode full
```

```bash
docker compose restart migrate worker
```

---

# Second batch (checked 2026-11-13)

The same method as above. On your request, Twilio, Figma, Airbnb, Pinterest, Robinhood, Dropbox, Reddit, Instacart, Lyft, Discord, Tower Research and Graviton were added to `sources.yaml`; the rest are not.

## Worth adding next (India jobs and internships)

| Company | Platform | Board URL to paste | Jobs read / site total | India | Intern-like |
|---|---|---|---|---|---|
| Tower Research Capital | Greenhouse | `https://boards.greenhouse.io/towerresearchcapital` | 93 / 93 | 10 | 16 |
| Airbnb | Greenhouse | `https://boards.greenhouse.io/airbnb` | 214 / 214 | 14 | 7 |
| Graviton Research | Greenhouse | `https://boards.greenhouse.io/gravitonresearchcapital` | 21 / 21 | 12 | 2 |
| Cadence | Workday | `https://cadence.wd1.myworkdayjobs.com/External_Careers` | 60 / 687 | 10 | 4 |
| Marvell | Workday | `https://marvell.wd1.myworkdayjobs.com/MarvellCareers` | 60 / 342 | 4 | 6 |
| Ciena | Workday | `https://ciena.wd5.myworkdayjobs.com/Careers` | 60 / 176 | 7 | 4 |
| Figma | Greenhouse | `https://boards.greenhouse.io/figma` | 143 / 143 | 2 | 9 |
| Applied Materials | Workday | `https://amat.wd1.myworkdayjobs.com/External` | 60 / 2,000 | 6 | 1 |

Applied Materials reports exactly 2,000 jobs, which is Workday's cap. It needs `split_facets: [locationCountry]` (as Micron has) for the nightly sweep to be complete.

## They work, but less useful now

| Company | Platform | Board URL | India | Intern-like | Why it's lower |
|---|---|---|---|---|---|
| Twilio | Greenhouse | `https://boards.greenhouse.io/twilio` | 11 | 0 | No internships right now |
| Druva | Greenhouse | `https://boards.greenhouse.io/druva` | 10 | 0 | No internships right now |
| Sprinklr | Workday | `https://sprinklr.wd1.myworkdayjobs.com/careers` | 9 | 0 | No internships right now |
| BlackRock | Workday | `https://blackrock.wd1.myworkdayjobs.com/BlackRock_Professional` | 6 | 0 | No internships on this board (campus roles may be elsewhere) |
| Workday | Workday | `https://workday.wd5.myworkdayjobs.com/Workday` | 2 | 0 | Few India jobs |
| Pinterest, Lyft, Robinhood | Greenhouse | `boards.greenhouse.io/<name>` | 0 | 17, 19, 3 | Internships, but none in India |
| Dropbox, Reddit, Instacart, Discord | Greenhouse | `boards.greenhouse.io/<name>` | 0 | 0 | Neither |

## Didn't work: the board URL guessed was wrong

| Company | Tried | Answer |
|---|---|---|
| Nutanix | Workday `Nutanix_Careers`, Greenhouse `nutanix` | 422, 404 |
| Synopsys | Workday `synopsys.wd1…/Careers` | 422 |
| NXP | Workday `nxp.wd3…/careers` | 422 |
| Lam Research | Workday `lamresearch.wd1…/LAM` | 422 |
| Zscaler | Workday `zscaler.wd1…/Zscaler_Careers` | 422 |
| Expedia | Workday `expedia.wd5…/search` | 422 |
| Chargebee | Greenhouse `chargebee` | 404 |
| Zepto, Upstox, Cars24 | Lever `zeptonow` / `zepto`, `upstox`, `cars24` | 404 |

On Workday, a 422 means the company is on Workday but the site name is wrong. Each company's real board URL is in the Apply links on its careers site; paste that into Add company.

---

# Third batch: quant, banking, big tech (checked 2026-11-13)

**Added to `sources.yaml`:**

| Company | Platform | Board | Jobs read / site total | India | Intern-like |
|---|---|---|---|---|---|
| IMC Trading | Greenhouse | `imc` | 158 / 158 | 16 | 17 |
| Jump Trading | Greenhouse | `jumptrading` | 92 / 92 | 4 | 28 |
| Squarepoint Capital | Greenhouse | `squarepointcapital` | 91 / 91 | 23 | 5 |
| Qube Research & Technologies | Greenhouse | `quberesearchandtechnologies` | 210 / 210 | 5 | 16 |
| WorldQuant | Greenhouse | `worldquant` | 82 / 82 | 8 | 2 |
| Hudson River Trading | Greenhouse | `wehrtyou` | 82 / 82 | 1 | 5 |
| DRW | Greenhouse | `drweng` | 159 / 159 | 0 | 10 |
| Virtu Financial | Greenhouse | `virtu` | 45 / 45 | 0 | 13 |
| Five Rings | Greenhouse | `fiveringsllc` | 19 / 19 | 0 | 4 |
| Akuna Capital | Greenhouse | `akunacapital` | 31 / 31 | 0 | 3 |
| Jane Street | Greenhouse | `janestreet` | 217 / 217 | 0 | 0 |
| Citi | Workday | `citi.wd5…/2` (split by country) | 60 / 2,000 | 26 | 0 |
| Northern Trust | Workday | `ntrs.wd1…/northerntrust` | 60 / 657 | 19 | 0 |
| LSEG | Workday | `lseg.wd3…/Careers` | 60 / 676 | 14 | 2 |
| S&P Global | Workday | `spgi.wd5…/SPGI_Careers` | 60 / 344 | 10 | 6 |
| Nasdaq | Workday | `nasdaq.wd1…/Global_External_Site` | 60 / 176 | 6 | 4 |
| Capital One | Workday | `capitalone.wd12…/Capital_One` (split by country) | 60 / 2,062 | 1 | 2 |
| Okta | Greenhouse | `okta` | 364 / 364 | 100 | 0 |
| GitLab | Greenhouse | `gitlab` | 253 / 253 | 37 | 0 |
| Elastic | Greenhouse | `elastic` | 398 / 398 | 19 | 0 |
| HP Inc | Workday | `hp.wd5…/ExternalCareerSite` | 60 / 931 | 2 | 5 |
| Zoom | Workday | `zoom.wd5…/Zoom` | 60 / 69 | 2 | 0 |

Jane Street showed no intern-like titles in this read, even though it hires interns every year. Its internship titles may not use the words the rules look for, so check what its first runs classify as internships.

**Answered with 0 jobs** (the board exists but is empty, so it's probably not the one they use):
- **Optiver:** Greenhouse `optiver`.
- **Millennium:** Workday `mlp.wd5…/mlpcareers`.

**Not found:**

| Company | Tried | Answer |
|---|---|---|
| Two Sigma, Citadel, Old Mission | Greenhouse | 404 (Two Sigma and Citadel run their own careers sites) |
| Arcesium, AlphaGrep, Quadeye | Greenhouse and Lever | 404 |
| BNY | Eightfold `bnymellon.eightfold.ai` | 404 |
| NatWest | Workday `rbs.wd3…/natwestgroup` | 404 |
| FactSet, Moody's, Palo Alto Networks | Workday | 422: the site name is wrong |
| MSCI, Intuit | Workday | 401: the board needs a login, so these are out of scope |
| Snowflake, Grab | Greenhouse | 404 |
| Canva, Atlan | Lever | 404 |
| Zepto | Greenhouse `zepto`, `zeptonow`; Lever `zepto`, `zeptonow`, `zeptoindia` | 404 everywhere. It probably uses its own site or Darwinbox, so it needs its real careers URL |
