/** Mirrors app/api/schemas.py. */

export type Elig = "ok" | "warn" | "pending";
export type Tag = "liked" | "applied" | "dismissed";

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
  closed: boolean;
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
  event_date: string | null;
  note: string | null;
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
}

export interface Stats {
  new_today: number;
  open_tech: number;
  companies: number;
  liked: number;
  applied: number;
  last_applied_at: string | null;
}

export interface SourceHealth {
  key: string;
  company: string;
  adapter: string;
  origin: string;
  enabled: boolean;
  status: "ok" | "failing" | "never_run";
  last_success_at: string | null;
  last_job_count: number | null;
  last_error: string | null;
  consecutive_failures: number;
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
