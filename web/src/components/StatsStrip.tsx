import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { type Filters, isPreset, type Preset, PRESETS } from "../filters";
import { day } from "../format";
import type { Stats } from "../types";

type Props = { f: Filters; set: (patch: Partial<Filters>) => void };

/**
 * The four numbers. Each one is a button that shows the jobs it counts (see PRESETS).
 * Phones get one sideways-scrolling row of chips; wider screens get tiles.
 */
export function StatsStrip({ f, set }: Props) {
  const { data } = useQuery({ queryKey: ["stats"], queryFn: () => api<Stats>("/api/stats") });
  const tiles: { preset: Preset; label: string; short: string; value?: number; sub: string }[] = [
    { preset: "new", label: "New today", short: "New today", value: data?.new_today, sub: "tech internships" },
    {
      preset: "open",
      label: "Open tech internships",
      short: "Open",
      value: data?.open_tech,
      sub: data ? `across ${data.companies} companies` : "",
    },
    { preset: "liked", label: "Liked", short: "Liked", value: data?.liked, sub: "saved for later" },
    {
      preset: "applied",
      label: "Applied",
      short: "Applied",
      value: data?.applied,
      sub: data?.last_applied_at ? `last on ${day(data.last_applied_at)}` : "none yet",
    },
  ];
  return (
    <section
      aria-label="Stats"
      className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:grid md:grid-cols-4 md:gap-3 md:overflow-visible md:px-0"
    >
      {tiles.map((t) => {
        const on = isPreset(f, PRESETS[t.preset]);
        return (
          <button
            key={t.preset}
            type="button"
            aria-pressed={on}
            onClick={() => set(PRESETS[t.preset])}
            className={`flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-[13px] whitespace-nowrap md:block md:h-auto md:rounded-xl md:px-4 md:py-3.5 md:text-left ${
              on
                ? "border-ok-bd bg-ok-bg font-medium text-ok-fg md:ring-3 md:ring-ring"
                : "border-line bg-surface text-ink hover:border-muted/40"
            }`}
          >
            <span className="md:hidden">{t.short}</span>
            <span className={`hidden text-xs font-medium md:block ${on ? "" : "text-muted"}`}>{t.label}</span>
            <span className="text-[15px] font-bold md:mt-0.5 md:block md:text-[26px]">{t.value ?? "–"}</span>
            <span className={`hidden text-xs md:block ${on ? "" : "text-muted"}`}>{t.sub || " "}</span>
          </button>
        );
      })}
    </section>
  );
}
