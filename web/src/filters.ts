import { useCallback, useEffect } from "react";
import { useSearchParams } from "react-router";
import type { Elig } from "./types";

export type TagFilter = "liked" | "applied" | "untagged";
export type Posted = "1d" | "7d" | "30d" | "any";

export type Filters = {
  view: "tech" | "all";
  company: string[];
  loc: string;
  elig: Elig[];
  posted: Posted;
  tag: TagFilter[];
  dismissed: boolean;
  /** First seen since midnight IST: the "New today" stat. */
  newToday: boolean;
  q: string;
};

/** Plan D5: tech internships, anywhere, any date. */
export const DEFAULTS: Filters = {
  view: "tech",
  company: [],
  loc: "anywhere",
  elig: [],
  posted: "any",
  tag: [],
  dismissed: false,
  newToday: false,
  q: "",
};

const ELIG: readonly Elig[] = ["ok", "warn", "pending"];
const TAGS: readonly TagFilter[] = ["liked", "applied", "untagged"];
const POSTED: readonly Posted[] = ["1d", "7d", "30d", "any"];
const KEYS = ["view", "company", "loc", "elig", "posted", "tag", "dismissed", "new", "q"] as const;
const STORE = "filters";

/** Only values that differ from DEFAULTS; list values repeat, as the API expects. */
export function toParams(f: Filters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.view !== DEFAULTS.view) p.set("view", f.view);
  f.company.forEach((c) => p.append("company", c));
  if (f.loc !== DEFAULTS.loc) p.set("loc", f.loc);
  f.elig.forEach((e) => p.append("elig", e));
  if (f.posted !== DEFAULTS.posted) p.set("posted", f.posted);
  f.tag.forEach((t) => p.append("tag", t));
  if (f.dismissed) p.set("dismissed", "true");
  if (f.newToday) p.set("new", "today");
  if (f.q.trim()) p.set("q", f.q.trim());
  return p;
}

function oneOf<T extends string>(v: string | null, allowed: readonly T[], fallback: T): T {
  return v !== null && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
}

export function fromParams(p: URLSearchParams): Filters {
  const loc = p.get("loc");
  return {
    view: p.get("view") === "all" ? "all" : "tech",
    company: p.getAll("company").filter((c) => /^[a-z0-9-]+$/.test(c)),
    loc: loc && /^(anywhere|india|[A-Z]{2})$/.test(loc) ? loc : DEFAULTS.loc,
    elig: p.getAll("elig").filter((e): e is Elig => (ELIG as readonly string[]).includes(e)),
    posted: oneOf(p.get("posted"), POSTED, DEFAULTS.posted),
    tag: p.getAll("tag").filter((t): t is TagFilter => (TAGS as readonly string[]).includes(t)),
    dismissed: p.get("dismissed") === "true",
    newToday: p.get("new") === "today",
    q: p.get("q") ?? "",
  };
}

export function activeCount(f: Filters): number {
  return (
    f.company.length +
    (f.loc !== DEFAULTS.loc ? 1 : 0) +
    f.elig.length +
    (f.posted !== DEFAULTS.posted ? 1 : 0) +
    f.tag.length +
    (f.dismissed ? 1 : 0) +
    (f.newToday ? 1 : 0)
  );
}

export type Preset = "new" | "open" | "liked" | "applied";

/**
 * What each stat tile shows, as a whole filter set, so the list matches the tile's number.
 * Liked and Applied count every tagged job, closed and non-tech ones included, hence "all".
 */
export const PRESETS: Record<Preset, Filters> = {
  new: { ...DEFAULTS, newToday: true },
  open: DEFAULTS,
  liked: { ...DEFAULTS, view: "all", tag: ["liked"] },
  applied: { ...DEFAULTS, view: "all", tag: ["applied"] },
};

export function isPreset(f: Filters, preset: Filters): boolean {
  return toParams(f).toString() === toParams(preset).toString();
}

function save(f: Filters) {
  try {
    // Not the search text, and not "new today", which would be stale tomorrow.
    localStorage.setItem(STORE, toParams({ ...f, q: "", newToday: false }).toString());
  } catch {
    // storage blocked
  }
}

/** Filters live in the URL; the last-used ones (minus search text) are remembered (plan D5). */
export function useFilters(): [Filters, (patch: Partial<Filters>) => void] {
  const [params, setParams] = useSearchParams();
  const hasFilters = KEYS.some((k) => params.has(k));

  useEffect(() => {
    if (hasFilters) return;
    try {
      const saved = localStorage.getItem(STORE);
      if (saved) {
        const next = new URLSearchParams(saved);
        params.forEach((v, k) => next.append(k, v)); // keep ?job=
        if (next.toString() !== params.toString()) setParams(next, { replace: true });
      }
    } catch {
      // storage blocked
    }
    // first load only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filters = fromParams(params);
  const update = useCallback(
    (patch: Partial<Filters>) => {
      setParams(
        (prev) => {
          const next = { ...fromParams(prev), ...patch };
          save(next);
          const out = toParams(next);
          const job = prev.get("job");
          if (job) out.set("job", job);
          return out;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  return [filters, update];
}
