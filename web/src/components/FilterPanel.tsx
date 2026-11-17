import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { api } from "../api";
import { activeCount, DEFAULTS, type Filters, type Posted, type TagFilter } from "../filters";
import { ELIG_LABEL } from "../format";
import type { Category, Elig, FilterOptions } from "../types";
import { Chip, card, label } from "./ui";

const TOP_COMPANIES = 8;
const select =
  "h-11 w-full rounded-lg border border-line bg-surface px-2 text-ink lg:h-[38px]";

function toggle<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

type Props = { f: Filters; set: (p: Partial<Filters>) => void; children?: ReactNode };

export function FilterPanel({ f, set, children }: Props) {
  const [allCompanies, setAllCompanies] = useState(false);
  const { data } = useQuery({
    queryKey: ["filters", f.view],
    queryFn: () => api<FilterOptions>(`/api/filters?view=${f.view}`),
  });
  const companies = data?.companies ?? [];
  const categories = data?.categories ?? [];
  // Keep ticked companies visible even when they're outside the top list.
  const shown = allCompanies
    ? companies
    : companies.filter((c, i) => i < TOP_COMPANIES || f.company.includes(c.value));
  const tab = (on: boolean) =>
    `h-9 flex-1 rounded-[9px] text-[13px] font-semibold ${on ? "bg-ink text-bg" : "text-muted hover:text-ink"}`;

  return (
    <aside aria-label="Filters" className="flex flex-col gap-4">
      <div className={`${card} flex p-1`} role="group" aria-label="Which jobs">
        <button type="button" aria-pressed={f.view === "tech"} className={tab(f.view === "tech")} onClick={() => set({ view: "tech", company: [] })}>
          Tech internships
        </button>
        <button type="button" aria-pressed={f.view === "all"} className={tab(f.view === "all")} onClick={() => set({ view: "all", company: [] })}>
          All jobs
        </button>
      </div>

      <div className={`${card} flex flex-col gap-4 p-4`}>
        <fieldset>
          <legend className={label}>Company</legend>
          {shown.map((c) => (
            <label key={c.value} className="flex min-h-9 items-center gap-2 py-0.5 lg:min-h-0 lg:py-1">
              <input
                type="checkbox"
                className="h-4 w-4 accent-accent"
                checked={f.company.includes(c.value)}
                onChange={() => set({ company: toggle(f.company, c.value) })}
              />
              <span className="flex-1">{c.label}</span>
              <span className="text-xs text-muted">{c.count}</span>
            </label>
          ))}
          {companies.length > TOP_COMPANIES && (
            <button type="button" className="mt-1 text-[13px] text-accent hover:underline" onClick={() => setAllCompanies(!allCompanies)}>
              {allCompanies ? "Show fewer" : `+ ${companies.length - TOP_COMPANIES} more`}
            </button>
          )}
          {companies.length === 0 && <p className="text-[13px] text-muted">No companies yet</p>}
        </fieldset>

        {categories.length > 0 && (
          <fieldset>
            <legend className={label}>Category</legend>
            <div className="flex flex-wrap gap-1.5">
              {categories.map((c) => (
                <Chip
                  key={c.value}
                  on={f.category.includes(c.value as Category)}
                  onClick={() => set({ category: toggle(f.category, c.value as Category) })}
                >
                  {c.label} <span className="text-xs opacity-70">{c.count}</span>
                </Chip>
              ))}
            </div>
          </fieldset>
        )}

        <div>
          <label htmlFor="loc" className={label}>
            Location
          </label>
          <select id="loc" className={select} value={f.loc} onChange={(e) => set({ loc: e.target.value })}>
            <option value="anywhere">Anywhere</option>
            <option value="india">India + Remote</option>
            {(data?.countries ?? []).map((c) => (
              <option key={c.value} value={c.value}>
                {c.label} ({c.count})
              </option>
            ))}
          </select>
        </div>

        <fieldset>
          <legend className={label}>Eligibility</legend>
          <div className="flex flex-wrap gap-1.5">
            {(["ok", "warn", "pending"] as Elig[]).map((e) => (
              <Chip key={e} on={f.elig.includes(e)} onClick={() => set({ elig: toggle(f.elig, e) })}>
                {ELIG_LABEL[e]}
              </Chip>
            ))}
          </div>
        </fieldset>

        <div>
          <label htmlFor="posted" className={label}>
            Posted
          </label>
          <select id="posted" className={select} value={f.posted} onChange={(e) => set({ posted: e.target.value as Posted })}>
            <option value="any">Any time</option>
            <option value="1d">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
          <div className="mt-2">
            <Chip on={f.newToday} onClick={() => set({ newToday: !f.newToday })}>
              First seen today
            </Chip>
          </div>
        </div>

        <fieldset>
          <legend className={label}>Tag</legend>
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                ["liked", "Liked"],
                ["applied", "Applied"],
                ["untagged", "Untagged"],
              ] as [TagFilter, string][]
            ).map(([t, name]) => (
              <Chip key={t} on={f.tag.includes(t)} onClick={() => set({ tag: toggle(f.tag, t) })}>
                {name}
              </Chip>
            ))}
          </div>
        </fieldset>

        <label className="flex min-h-9 items-center gap-2">
          <input type="checkbox" className="h-4 w-4 accent-accent" checked={f.dismissed} onChange={(e) => set({ dismissed: e.target.checked })} />
          Show dismissed
        </label>

        {activeCount(f) > 0 && (
          <button
            type="button"
            className="self-start text-[13px] text-accent hover:underline"
            onClick={() => set({ ...DEFAULTS, view: f.view, q: f.q })}
          >
            Clear filters
          </button>
        )}
      </div>
      {children}
    </aside>
  );
}
