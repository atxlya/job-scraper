import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import { Header } from "../components/Header";
import { card } from "../components/ui";
import { ago } from "../format";
import type { SourceHealth } from "../types";

const STATUS = {
  ok: ["OK", "border-ok-bd bg-ok-bg text-ok-fg"],
  failing: ["Failing", "border-warn-bd bg-warn-bg text-warn-fg"],
  never_run: ["Not run yet", "border-line bg-chip text-muted"],
} as const;

const PLATFORM: Record<string, string> = {
  workday: "Workday",
  eightfold: "Eightfold",
  oracle_hcm: "Oracle HCM",
  google: "Google (own site)",
  barclays: "Barclays (own site)",
  lever: "Lever",
  greenhouse: "Greenhouse",
  amazon: "Amazon (own site)",
  apple: "Apple (own site)",
  atlassian: "Atlassian (own site)",
  amd: "AMD (own site)",
  ibm: "IBM (own site)",
  capgemini: "Capgemini (own site)",
  phonepe: "PhonePe (own site)",
  swiggy: "Swiggy (own site)",
  zerodha: "Zerodha (own site)",
  successfactors: "SuccessFactors",
  rss: "RSS feed",
  notice_page: "Notice page",
  sitemap_partial: "Sitemap (titles only)",
  tataelxsi: "Tata Elxsi (own site)",
};

export function Sources() {
  const navigate = useNavigate();
  const { data, error } = useQuery({ queryKey: ["sources"], queryFn: () => api<SourceHealth[]>("/api/sources") });
  const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted";
  const td = "px-3 py-2.5 align-top";
  return (
    <div className="min-h-screen bg-bg">
      <Header q="" onSearch={(q) => navigate(q ? `/?q=${encodeURIComponent(q)}` : "/")} />
      <main className="mx-auto flex max-w-[1360px] flex-col gap-3 px-4 pt-4 pb-10 lg:px-6">
        <Link to="/" className="self-start text-[13px] text-accent hover:underline">
          ← All jobs
        </Link>
        <h1 className="m-0 text-lg font-bold">Sources</h1>
        {error && <p role="alert">Couldn't load sources.</p>}
        <div className={`${card} overflow-x-auto`}>
          <table className="w-full min-w-[820px] border-collapse text-[13px]">
            <thead className="border-b border-line">
              <tr>
                <th className={th}>Company</th>
                <th className={th}>Source</th>
                <th className={th}>Platform</th>
                <th className={th}>Status</th>
                <th className={th}>Last success</th>
                <th className={th}>Jobs</th>
                <th className={th}>Last error</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((s) => {
                const [label, cls] = STATUS[s.status];
                return (
                  <tr key={s.key} className={`border-b border-line last:border-0 ${s.enabled ? "" : "opacity-60"}`}>
                    <td className={`${td} font-medium`}>{s.company}</td>
                    <td className={td}>
                      {s.key}
                      {s.origin === "dashboard" && <span className="ml-1.5 text-xs text-muted">(added here)</span>}
                      {!s.enabled && <span className="ml-1.5 text-xs text-muted">(off)</span>}
                    </td>
                    <td className={td}>{PLATFORM[s.adapter] ?? s.adapter}</td>
                    <td className={td}>
                      <span className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}>
                        {label}
                        {s.status === "failing" ? ` · ${s.consecutive_failures}×` : ""}
                      </span>
                    </td>
                    <td className={`${td} whitespace-nowrap`}>{s.last_success_at ? ago(s.last_success_at) : "—"}</td>
                    <td className={td}>{s.last_job_count ?? "—"}</td>
                    <td className={`${td} max-w-[360px] break-words text-muted`}>
                      {/* A recovered source keeps its old error in the DB; only show it while failing. */}
                      {s.status === "failing" ? s.last_error : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
