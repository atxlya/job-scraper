import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import { Header } from "../components/Header";
import { NightsChart } from "../components/NightsChart";
import { card } from "../components/ui";
import { ago, clockIST, dayTimeIST, duration, until } from "../format";
import { useMedia, WIDE } from "../hooks";
import type { Run, RunStatus, Schedule, SourceHealth } from "../types";

type Status = SourceHealth["status"];

const STATUS: Record<Status, [string, string, string]> = {
  failing: ["Failing", "⚠", "border-warn-bd bg-warn-bg text-warn-fg"],
  partial: ["Partial", "◐", "border-line bg-chip text-ink"],
  warning: ["Count dropped", "↘", "border-warn-bd bg-warn-bg text-warn-fg"],
  ok: ["OK", "✓", "border-ok-bd bg-ok-bg text-ok-fg"],
  never_run: ["Not run yet", "·", "border-line bg-chip text-muted"],
};

const RUN_STATUS: Record<RunStatus, string> = {
  ok: "border-ok-bd bg-ok-bg text-ok-fg",
  partial: "border-line bg-chip text-ink",
  failed: "border-warn-bd bg-warn-bg text-warn-fg",
};

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
  techmahindra: "Tech Mahindra (own site)",
  ripplehire: "RippleHire",
  spire2grow: "Spire2Grow",
  mynexthire: "MyNextHire",
  jio: "Jio (own site)",
  ril: "Reliance (own site)",
};

function StatusPill({ s }: { s: SourceHealth }) {
  const [label, icon, cls] = STATUS[s.status];
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}>
      <span aria-hidden="true">{icon}</span>
      {label}
      {s.status === "failing" ? ` · ${s.consecutive_failures}×` : ""}
    </span>
  );
}

function lastRun(s: SourceHealth): string {
  if (!s.last_run) return "—";
  return `${s.last_run.kind} · ${duration(s.last_run.duration_s)} · ${ago(s.last_run.started_at)}`;
}

/** A recovered source keeps its old error in the DB; only show it while the source isn't healthy. */
function shownError(s: SourceHealth): string | null {
  return s.status === "failing" ? s.last_error : null;
}

function Summary({ rows }: { rows: SourceHealth[] }) {
  const { data: schedule } = useQuery({ queryKey: ["schedule"], queryFn: () => api<Schedule>("/api/schedule") });
  const on = rows.filter((r) => r.enabled);
  const count = (st: Status[]) => on.filter((r) => st.includes(r.status)).length;
  const parts: [number, string, string][] = [
    [count(["ok"]), "OK", "bg-ok-fg"],
    [count(["partial"]), "partial", "bg-muted"],
    [count(["warning"]), "count dropped", "bg-warn-fg"],
    [count(["failing"]), "failing", "bg-bad"],
    [count(["never_run"]), "not run yet", "bg-line"],
    [rows.length - on.length, "off", "bg-line"],
  ];
  const shown = parts.filter(([n], i) => n > 0 || i === 0 || i === 3);
  return (
    <p data-testid="summary" className="m-0 flex flex-wrap items-center gap-y-1 text-[13px] whitespace-pre text-muted">
      {shown.map(([n, label, dot], i) => (
        <Fragment key={label}>
          {i > 0 && <span aria-hidden="true"> · </span>}
          <span className="inline-flex items-center gap-1.5">
            <span className={`inline-block h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
            <strong className="text-ink">{n}</strong> {label}
          </span>
        </Fragment>
      ))}
      {schedule && (
        <>
          <span aria-hidden="true"> · </span>
          <span>
            Next full sweep {clockIST(schedule.next_full_at)} IST ({until(schedule.next_full_at)})
          </span>
        </>
      )}
    </p>
  );
}

function Runs({ k }: { k: string }) {
  const { data, error } = useQuery({ queryKey: ["runs", k], queryFn: () => api<Run[]>(`/api/sources/${k}/runs`) });
  if (error) return <p role="alert" className="m-0 text-[13px] text-warn-fg">Couldn't load the runs.</p>;
  if (!data) return <p className="m-0 text-[13px] text-muted">Loading runs…</p>;
  if (data.length === 0) return <p className="m-0 text-[13px] text-muted">No runs yet.</p>;
  const th = "px-2.5 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-muted";
  const td = "px-2.5 py-1.5 align-top";
  return (
    <div className="overflow-x-auto rounded-[10px] border border-line bg-surface">
      <table aria-label={`Last runs of ${k}`} className="w-full min-w-[640px] border-collapse text-xs">
        <thead className="border-b border-line">
          <tr>
            <th className={th}>Kind</th>
            <th className={th}>Started</th>
            <th className={th}>Took</th>
            <th className={th}>Status</th>
            <th className={th}>Read / site total</th>
            <th className={th}>New</th>
            <th className={th}>Updated</th>
            <th className={th}>Closed</th>
            <th className={th}>Error</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.started_at + r.kind} className="border-b border-line last:border-0">
              <td className={`${td} ${r.kind === "full" ? "font-semibold" : ""}`}>{r.kind}</td>
              <td className={`${td} whitespace-nowrap`}>{dayTimeIST(r.started_at)}</td>
              <td className={`${td} whitespace-nowrap`}>{duration(r.duration_s)}</td>
              <td className={td}>
                <span className={`rounded-full border px-1.5 py-px font-semibold ${RUN_STATUS[r.status]}`}>{r.status}</span>
              </td>
              <td className={`${td} whitespace-nowrap`}>
                {r.jobs_found.toLocaleString("en-IN")} / {r.reported_total === null ? "—" : r.reported_total.toLocaleString("en-IN")}
              </td>
              <td className={td}>{r.new_count}</td>
              <td className={td}>{r.updated_count}</td>
              <td className={td}>{r.closed_count}</td>
              <td className={`${td} max-w-[320px] break-words text-warn-fg`}>{r.error}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Name({ s }: { s: SourceHealth }) {
  return (
    <span className="flex flex-col">
      <span data-testid="source-name" className="font-semibold">
        {s.company}
      </span>
      <span className="text-xs text-muted">
        {s.key} · {PLATFORM[s.adapter] ?? s.adapter}
        {s.origin === "dashboard" && " · added here"}
        {!s.enabled && " · off"}
      </span>
    </span>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true" className={`shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`}>
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

export function Sources() {
  const navigate = useNavigate();
  const wide = useMedia(WIDE);
  const [open, setOpen] = useState<string | null>(null);
  const { data, error } = useQuery({ queryKey: ["sources"], queryFn: () => api<SourceHealth[]>("/api/sources") });
  const rows = data ?? [];
  const toggle = (k: string) => setOpen(open === k ? null : k);
  const th = "px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-muted";
  const td = "px-3 py-2.5 align-middle";
  return (
    <div className="min-h-screen bg-bg">
      <Header q="" onSearch={(q) => navigate(q ? `/?q=${encodeURIComponent(q)}` : "/")} />
      <main className="mx-auto flex max-w-[1360px] flex-col gap-3 px-4 pt-4 pb-10 lg:px-6">
        <Link to="/" className="self-start text-[13px] text-accent hover:underline">
          ← All jobs
        </Link>
        <h1 className="m-0 text-lg font-bold">Sources</h1>
        {error && <p role="alert">Couldn't load sources.</p>}
        {data && <Summary rows={rows} />}
        {wide ? (
          <div className={card}>
            <table className="w-full border-collapse text-[13px]">
              <thead className="border-b border-line">
                <tr>
                  <th className={th}>Company · source</th>
                  <th className={th}>Status</th>
                  <th className={th}>Last 14 nights</th>
                  <th className={`${th} text-right`}>Jobs</th>
                  <th className={th}>Last run</th>
                  <th className={th}>Last error</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <Fragment key={s.key}>
                    <tr
                      className={`border-b border-line hover:bg-chip ${open === s.key ? "bg-chip" : ""} ${s.enabled ? "" : "opacity-60"}`}
                      onClick={() => toggle(s.key)}
                    >
                      <td className={td}>
                        <button
                          type="button"
                          aria-expanded={open === s.key}
                          className="flex items-center gap-2 text-left"
                          onClick={(e) => {
                            e.stopPropagation();
                            toggle(s.key);
                          }}
                        >
                          <Chevron open={open === s.key} />
                          <Name s={s} />
                        </button>
                      </td>
                      <td className={td}>
                        <StatusPill s={s} />
                      </td>
                      <td className={td}>
                        <NightsChart nights={s.nights} />
                      </td>
                      <td className={`${td} text-right tabular-nums`}>{s.last_job_count?.toLocaleString("en-IN") ?? "—"}</td>
                      <td className={`${td} whitespace-nowrap text-muted`}>{lastRun(s)}</td>
                      <td className={`${td} max-w-[300px] break-words text-warn-fg`}>{shownError(s)}</td>
                    </tr>
                    {open === s.key && (
                      <tr className="border-b border-line bg-chip">
                        <td colSpan={6} className="px-3 pt-1 pb-3 pl-9">
                          <Runs k={s.key} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
            {rows.map((s) => (
              <li key={s.key} className={`${card} ${s.enabled ? "" : "opacity-60"}`}>
                <button
                  type="button"
                  aria-expanded={open === s.key}
                  className="flex w-full flex-col gap-2 px-3.5 py-3 text-left"
                  onClick={() => toggle(s.key)}
                >
                  <span className="flex items-start justify-between gap-2">
                    <Name s={s} />
                    <StatusPill s={s} />
                  </span>
                  <span className="flex items-end justify-between gap-3">
                    <span className="flex flex-col">
                      <span className="text-xl leading-none font-bold tabular-nums">{s.last_job_count?.toLocaleString("en-IN") ?? "—"}</span>
                      <span className="mt-1 text-xs text-muted">jobs · {lastRun(s)}</span>
                    </span>
                    <NightsChart nights={s.nights} />
                  </span>
                  {shownError(s) && <span className="text-xs break-words text-warn-fg">{shownError(s)}</span>}
                </button>
                {open === s.key && (
                  <div className="px-3.5 pb-3">
                    <Runs k={s.key} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
