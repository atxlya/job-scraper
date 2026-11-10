import { Link } from "react-router";
import { ago, initials, TAG_LABEL } from "../format";
import type { JobCard as Card } from "../types";
import { EligBadge } from "./ui";

type Props = { job: Card; to: string; selected: boolean; now?: Date };

export function JobCard({ job, to, selected, now }: Props) {
  const when = job.posted_at ? ago(job.posted_at, now) : `seen ${ago(job.first_seen_at, now)}`;
  const meta = [job.company, job.location, when].filter(Boolean).join(" · ");
  return (
    <Link
      to={to}
      aria-current={selected ? "true" : undefined}
      className={`grid w-full grid-cols-1 gap-x-3 gap-y-2 rounded-xl border bg-surface px-4 py-3.5 text-ink no-underline sm:grid-cols-[auto_1fr_auto] sm:items-center ${
        selected ? "border-accent ring-3 ring-ring" : "border-line hover:border-muted/40"
      }`}
    >
      <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-chip text-[13px] font-bold sm:flex" aria-hidden="true">
        {initials(job.company)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {job.is_new && (
            <span className="rounded bg-accent px-1.5 py-px text-[11px] font-bold text-on-accent">
              NEW
            </span>
          )}
          <span className="text-[15px] font-semibold">{job.title}</span>
        </div>
        <div className="mt-0.5 text-[13px] text-muted sm:truncate">{meta}</div>
      </div>
      <Badges job={job} className="flex-wrap sm:flex-col sm:items-end" />
    </Link>
  );
}

/** Eligibility, closed and tag badges: a right-hand column on wide cards, a row under the text on phones. */
function Badges({ job, className }: { job: Card; className: string }) {
  return (
    <div className={`flex gap-1.5 ${className}`}>
      <EligBadge status={job.eligibility} />
      {job.closed && (
        <span className="rounded-full border border-line bg-chip px-2 py-px text-xs text-muted">
          Closed
        </span>
      )}
      {job.tag && (
        <span className="rounded-full border border-line px-2 py-px text-xs">{TAG_LABEL[job.tag]}</span>
      )}
    </div>
  );
}
