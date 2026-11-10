import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { day } from "../format";
import type { Stats } from "../types";
import { card } from "./ui";

export function StatsStrip() {
  const { data } = useQuery({ queryKey: ["stats"], queryFn: () => api<Stats>("/api/stats") });
  const tiles = [
    { label: "New today", value: data?.new_today, sub: "tech internships" },
    {
      label: "Open tech internships",
      value: data?.open_tech,
      sub: data ? `across ${data.companies} companies` : "",
    },
    { label: "Liked", value: data?.liked, sub: "saved for later" },
    {
      label: "Applied",
      value: data?.applied,
      sub: data?.last_applied_at ? `last on ${day(data.last_applied_at)}` : "none yet",
    },
  ];
  return (
    <section aria-label="Stats" className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className={`${card} px-4 py-3.5`}>
          <div className="text-xs font-medium text-muted">{t.label}</div>
          <div className="mt-0.5 text-[26px] font-bold">{t.value ?? "–"}</div>
          <div className="text-xs text-muted">{t.sub || " "}</div>
        </div>
      ))}
    </section>
  );
}
