import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import { Header } from "../components/Header";
import { card } from "../components/ui";
import { shortDay, since, STAGE_LABEL } from "../format";
import { useMedia, WIDE } from "../hooks";
import type { Application, Stage, Step } from "../types";

type Group = "applied" | Stage;
/** Most advanced first; Rejected last. */
const ORDER: Group[] = ["offer", "interview", "oa", "applied", "rejected"];
const TONE: Record<Group, string> = {
  offer: "text-ok-fg",
  interview: "text-accent",
  oa: "text-ink",
  applied: "text-ink",
  rejected: "text-warn-fg",
};
const COLUMNS: ("applied" | "oa" | "interview")[] = ["applied", "oa", "interview"];

const last = (a: Application): Step | undefined => a.steps[a.steps.length - 1];

/** The date a stage was last reached in this application, or "—". */
function on(a: Application, s: Step["stage"]): string {
  const step = [...a.steps].reverse().find((st) => st.stage === s);
  return step ? shortDay(step.on) : "—";
}

function sinceLast(a: Application, short = false): string {
  const st = last(a);
  if (!st) return "";
  const label = STAGE_LABEL[st.stage];
  const ago = since(st.on);
  if (ago === "today") return `${label} today`;
  return short ? `${label} · ${ago} ago` : `${label} ${shortDay(st.on)} · ${ago}`;
}

function Closed() {
  return <span className="ml-1.5 rounded border border-warn-bd bg-warn-bg px-1.5 py-px text-[11px] font-semibold text-warn-fg">Closed</span>;
}

/** Every applied job, grouped by stage, closed ones too. The only place rejected ones are listed. */
export function Applications() {
  const navigate = useNavigate();
  const wide = useMedia(WIDE);
  const { data, error } = useQuery({ queryKey: ["applications"], queryFn: () => api<Application[]>("/api/applications") });
  const rows = data ?? [];
  const groups = ORDER.map((g) => ({ g, items: rows.filter((a) => (a.stage ?? "applied") === g) })).filter((x) => x.items.length);
  const count = (g: Group) => rows.filter((a) => (a.stage ?? "applied") === g).length;
  const summary = [
    `${rows.length} application${rows.length > 1 ? "s" : ""}`,
    count("offer") && `${count("offer")} offer${count("offer") > 1 ? "s" : ""}`,
    count("interview") && `${count("interview")} interviewing`,
    count("rejected") && `${count("rejected")} rejected`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="min-h-screen bg-bg">
      <Header q="" onSearch={(q) => navigate(q ? `/?q=${encodeURIComponent(q)}` : "/")} />
      <main className="mx-auto flex max-w-[1360px] flex-col gap-3 px-4 pt-4 pb-10 lg:px-6">
        <Link to="/" className="self-start text-[13px] text-accent hover:underline">
          ← All jobs
        </Link>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="m-0 text-lg font-bold">Your applications</h1>
          {rows.length > 0 && <span className="text-[13px] text-muted">{summary}</span>}
        </div>
        {error && <p role="alert">Couldn't load your applications.</p>}
        {data && rows.length === 0 && (
          <p className="m-0 text-muted">No applications yet. Mark a job Applied and it shows here, with each step after it.</p>
        )}
        {!wide && groups.length > 1 && (
          <nav aria-label="Stages" className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1">
            {groups.map(({ g, items }) => (
              <a key={g} href={`#stage-${g}`} className="shrink-0 rounded-full border border-line bg-surface px-3 py-1.5 text-[13px] text-ink no-underline">
                {STAGE_LABEL[g]} {items.length}
              </a>
            ))}
          </nav>
        )}
        {groups.map(({ g, items }) => (
          <section key={g} id={`stage-${g}`} aria-label={`${STAGE_LABEL[g]} · ${items.length}`} className="scroll-mt-3">
            <h2 className={`m-0 mb-1.5 text-[13px] font-semibold ${TONE[g]}`}>
              {STAGE_LABEL[g]} · {items.length}
            </h2>
            {g === "rejected" && (
              <p className="m-0 mb-1.5 text-xs text-muted">
                Your rejection history, newest first. These jobs are hidden from the job list; open one to see its steps
                and notes, or move it to another stage if it was a mistake.
              </p>
            )}
            {wide ? <Table items={items} /> : <Cards items={items} />}
          </section>
        ))}
      </main>
    </div>
  );
}

function Table({ items }: { items: Application[] }) {
  const th = "px-3 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-muted";
  const td = "px-3 py-2.5 align-middle";
  return (
    <div className={card}>
      <table className="w-full table-fixed border-collapse text-[13px]">
        <colgroup>
          <col />
          <col className="w-[110px]" />
          <col className="w-[110px]" />
          <col className="w-[110px]" />
          <col className="w-[200px]" />
        </colgroup>
        <thead className="border-b border-line">
          <tr>
            <th className={th}>Job</th>
            {COLUMNS.map((c) => (
              <th key={c} className={th}>
                {STAGE_LABEL[c]}
              </th>
            ))}
            <th className={th}>Since last step</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id} className="border-b border-line last:border-b-0 hover:bg-chip">
              <td className={td}>
                <Link to={`/jobs/${a.id}`} className="block min-w-0 text-ink no-underline">
                  <span className="block text-xs text-muted">
                    {a.company}
                    {a.closed && <Closed />}
                  </span>
                  <span className="block truncate font-semibold">{a.title}</span>
                </Link>
              </td>
              {COLUMNS.map((c) => (
                <td key={c} className={`${td} text-muted`}>
                  {on(a, c)}
                </td>
              ))}
              <td className={td}>{sinceLast(a)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Cards({ items }: { items: Application[] }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {items.map((a) => (
        <li key={a.id}>
          <Link to={`/jobs/${a.id}`} className={`${card} block px-3.5 py-3 text-ink no-underline`}>
            <span className="block text-xs text-muted">
              {a.company}
              {a.closed && <Closed />}
            </span>
            <span className="block font-semibold leading-snug">{a.title}</span>
            <span className="mt-1 block text-xs text-muted">
              {a.steps.map((st) => `${STAGE_LABEL[st.stage]} ${shortDay(st.on)}`).join(" · ")}
            </span>
            <span className="block text-xs text-muted">{sinceLast(a, true)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
