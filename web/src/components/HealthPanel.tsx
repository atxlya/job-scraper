import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api";
import type { SourceHealth } from "../types";
import { card } from "./ui";

export function HealthPanel() {
  const { data } = useQuery({ queryKey: ["sources"], queryFn: () => api<SourceHealth[]>("/api/sources") });
  const enabled = (data ?? []).filter((s) => s.enabled);
  const failing = enabled.filter((s) => s.status === "failing");
  const healthy = enabled.filter((s) => s.status === "ok").length;
  return (
    <section aria-label="Scraper health" className={`${card} p-4`}>
      <div className="mb-2.5 flex items-baseline justify-between">
        <h2 className="m-0 text-sm font-semibold">Scraper health</h2>
        <Link to="/sources" className="text-[13px] text-accent hover:underline">
          All sources
        </Link>
      </div>
      <div className="mb-1 flex gap-3 text-[13px] text-muted">
        <span>
          <strong className="text-ink">{data ? healthy : "–"}</strong> healthy
        </span>
        <span>
          <strong className={failing.length ? "text-warn-fg" : "text-ink"}>{data ? failing.length : "–"}</strong> failing
        </span>
      </div>
      {failing.map((s) => (
        <div key={s.key} className="flex items-start gap-2 border-t border-line py-2">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" className="mt-0.5 shrink-0 text-warn-fg">
            <path d="M12 9v4M12 17h.01" />
            <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
          </svg>
          <div className="min-w-0">
            <div className="font-medium">{s.company}</div>
            <div className="break-words text-xs text-muted">
              {s.consecutive_failures} failed run{s.consecutive_failures === 1 ? "" : "s"} in a row
              {s.last_error ? ` · ${s.last_error.slice(0, 120)}` : ""}
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}
