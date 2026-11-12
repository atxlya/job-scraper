# Same job posted in many places

Branch `same-job-groups`, 2026-11-12, cut from `application-stages`. This is prompt 7 in [next-prompts.md](next-prompts.md).

**Decision: not built.** The measurement below showed a small gain, and you chose not to build the grouping. Nothing in the code changed.

## Measured first (nothing built yet)

On a copy of the real database (`sqlite3 data/jobs.db ".backup …"`), 2026-11-12. Jobs are grouped by company plus title; the title is lower-cased, every run of punctuation is replaced with a space, and spaces are collapsed. Matching on the lower-cased title alone gives 11 groups instead of 13; the extra two differ only by a space before a dash, such as Adobe's "2027 Intern- Software Engineer" and "2027 Intern - Software Engineer".

| | Jobs | Cards after grouping | Fewer cards | Groups of 2+ | Biggest groups |
|---|---|---|---|---|---|
| Open tech internships (the default view) | 208 | 186 | 22 (11%) | 13 | 5, 4, 4, 3, 3, then eight of 2 |
| All open jobs | 1,359 | 1,187 | 172 (13%) | 86 | 20, 8, 7, 6, 6, 6, 6, 5 |

**Biggest groups among open tech internships:**

| Jobs | Company | Title | Locations |
|---|---|---|---|
| 5 | Visa | Consulting & Analytics Intern | Prague, Budapest, Bratislava, Stockholm, Paris |
| 4 | Adobe | 2027 Intern - Software Engineer | Basel, Bucharest, Yerevan, San Jose |
| 4 | Intel | AI Data Science / Software Engineering PhD Intern New 2027 | Santa Clara, and Hillsboro 3 times |
| 3 | Adobe | 2027 Intern - Security Engineer | Bucharest, San Jose, Lehi |
| 3 | Intel | Compiler Engineering Intern | Shanghai, Toronto, Gdansk |
| 2 each | Google ×2, NVIDIA ×2, Salesforce, Cisco, Microsoft, Intel | | |

**What this shows:**
- **Microsoft and Qualcomm aren't the problem in this data.**
  - Microsoft has one pair: "Cloud Solution Architecture INTERN", in Schiphol and Germany.
  - Qualcomm has none. Every Qualcomm title carries its own duration and city ("… - 6 months, Cork", "… - Canada (16 months)"), and no two titles are the same.
  - Grouping Qualcomm would mean cutting those endings off the title, which makes this a fuzzy match rather than an exact one.
- **Some groups aren't one job in many places.** At least 3 of the 13 hold the same location more than once: Intel Hillsboro ×3, NVIDIA Warsaw ×2, Salesforce Dublin ×2. These are separate postings (different job IDs) at one site, so "N locations" would be the wrong label for them.
- **In the default view, the gain is 22 fewer cards out of 208.** Most of it comes from Intel (6), Adobe (5) and Visa (4).
- **In "All jobs" the effect is bigger:** 172 fewer cards, led by Dell (37), KPMG India (18), BrowserStack (17), Morgan Stanley (16) and Oracle (16). But most of those are not internships.

## Decision

**Not built** (your call, 2026-11-12). The default view would lose only 22 of 208 cards, and the companies the prompt named (Microsoft, Qualcomm) barely repeat titles. *Cost:* the 13 repeated titles stay as separate cards. Each is still its own job, with its own tag and alert.

**When to measure again:** if the default view grows a lot, or a company starts posting one title per city. Run the same count on a fresh database copy; the method is described at the top of this file.
