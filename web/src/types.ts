/** Mirrors app/api/schemas.py. */

export type Elig = "ok" | "warn" | "pending";
export type Tag = "liked" | "applied" | "dismissed";
/** After Applied. A separate field: an applied job keeps the tag "applied" whatever its stage. */
export type Stage = "oa" | "interview" | "offer" | "rejected";
/** Kind of tech internship (app/core/categories.py), for choosing which resume to send. */
export type Category =
  | "swe"
  | "ml"
  | "data"
  | "hardware"
  | "cloud"
  | "security"
  | "quant"
  | "qa"
  | "research"
  | "it"
  | "other";

export interface JobCard {
  id: number;
  company: string;
  company_slug: string;
  title: string;
  /** Every location, joined: the card's tooltip. */
  location: string;
  /** "City, Country" of the first location. */
  place: string;
  /** ISO code of that country, for its flag. */
  country: string | null;
  more_places: number;
  india: boolean;
  remote: boolean;
  posted_at: string | null;
  first_seen_at: string;
  is_new: boolean;
  eligibility: Elig;
  tag: Tag | null;
  /** Only while tag is "applied". */
  stage: Stage | null;
  closed: boolean;
  /** Empty until Gemini or the title sorter has placed it. */
  category?: Category | null;
}

export interface JobPage {
  total: number;
  items: JobCard[];
  loaded_at: string;
  max_id: number;
}

export interface Option {
  value: string;
  label: string;
  count: number;
}

export interface FilterOptions {
  companies: Option[];
  countries: Option[];
  categories?: Option[];
}

export interface Sections {
  about?: string;
  responsibilities?: string[];
  requirements?: string[];
  preferred?: string[];
  eligibility?: string[];
}

export interface Change {
  at: string;
  fields: string[];
}

export interface TagEvent {
  at: string;
  from_tag: Tag | null;
  to_tag: Tag | null;
  /** A stage step has from_tag = to_tag = "applied". */
  from_stage: Stage | null;
  to_stage: Stage | null;
  event_date: string | null;
  note: string | null;
}

/** One step of the current application. `on` is a YYYY-MM-DD date. */
export interface Step {
  stage: "applied" | Stage;
  on: string;
  at: string;
  note: string | null;
}

export interface Application {
  id: number;
  company: string;
  company_slug: string;
  title: string;
  closed: boolean;
  stage: Stage | null;
  /** Oldest first. */
  steps: Step[];
  last_on: string;
}

export interface JobDetail extends JobCard {
  external_id: string;
  locations: string[];
  employment_type: string | null;
  remote_type: string | null;
  url: string;
  apply_url: string | null;
  degree: string | null;
  quote: string | null;
  checking: boolean;
  unclear: boolean;
  unchecked: "notice" | "partial" | "snippet" | null; // why Gemini never reads it
  tech_internship: boolean;
  sections: Sections | null;
  description_html: string | null;
  has_description: boolean;
  note: string | null;
  changes: Change[];
  tag_history: TagEvent[];
  /** The current application's steps, oldest first; empty unless applied. */
  steps: Step[];
}

export interface Stats {
  new_today: number;
  open_tech: number;
  companies: number;
  liked: number;
  /** Still in play. Rejected applications are counted apart and left out of the job list. */
  applied: number;
  rejected: number;
  last_applied_at: string | null;
}

export interface SourceHealth {
  key: string;
  company: string;
  adapter: string;
  origin: string;
  enabled: boolean;
  /** failing: failed runs in a row; partial: last run partial; warning: job count dropped. */
  status: "failing" | "partial" | "warning" | "ok" | "never_run";
  last_success_at: string | null;
  last_job_count: number | null;
  last_error: string | null;
  consecutive_failures: number;
  last_run: LastRun | null;
  /** The last 14 nights (IST), oldest first: the full sweep's read count. */
  nights: Night[];
}

export type RunStatus = "ok" | "partial" | "failed";

export interface LastRun {
  kind: "incremental" | "full" | "tracked";
  status: RunStatus;
  started_at: string;
  duration_s: number | null;
}

export interface Night {
  day: string;
  count: number | null;
  status: RunStatus | null;
}

export interface Run extends LastRun {
  jobs_found: number;
  reported_total: number | null;
  new_count: number;
  updated_count: number;
  closed_count: number;
  error: string | null;
}

export interface Schedule {
  incremental_minutes: number;
  full_at: string; // "02:00" IST
  tracked_at: string;
  next_full_at: string;
  next_tracked_at: string;
}

export interface Detected {
  adapter: string;
  config: Record<string, unknown>;
  key_hint: string;
}

export interface AddResult {
  key: string;
  jobs_found: number;
  sample_titles: string[];
}
