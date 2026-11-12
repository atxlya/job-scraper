import { Link } from "react-router";
import { ago, companyHue, flag, initials, TAG_LABEL } from "../format";
import { logoFor } from "../logos";
import type { JobCard as Card } from "../types";
import { EligBadge } from "./ui";

type Props = { job: Card; to: string; selected: boolean; now?: Date };

export function JobCard({ job, to, selected, now }: Props) {
  const when = job.posted_at ? ago(job.posted_at, now) : `seen ${ago(job.first_seen_at, now)}`;
  const where = [flag(job.country), job.place].filter(Boolean).join(" ");
  return (
    <Link
      to={to}
      aria-current={selected ? "true" : undefined}
      className={`grid w-full grid-cols-1 items-start gap-x-3 gap-y-2 rounded-xl border bg-surface px-4 py-3 text-ink no-underline sm:grid-cols-[auto_1fr_auto] ${
        selected ? "border-accent ring-3 ring-ring" : "border-line hover:border-muted/40"
      }`}
    >
      <CompanyIcon slug={job.company_slug} name={job.company} />
      <div className="min-w-0">
        <div className="line-clamp-2 text-[15px] leading-snug font-semibold">
          {job.is_new && (
            <span className="mr-1.5 inline-block rounded bg-accent px-1.5 align-[2px] text-[11px] leading-[16px] font-bold text-on-accent">
              NEW
            </span>
          )}
          {job.title}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px] text-muted" title={job.location}>
          <span>
            {job.company}
            {where && ` · ${where}`}
            {job.more_places > 0 && <span className="ml-1">+{job.more_places}</span>}
            {when && ` · ${when}`}
          </span>
          {job.india && <Mark india>India</Mark>}
          {job.remote && <Mark>Remote</Mark>}
        </div>
      </div>
      <Badges job={job} />
    </Link>
  );
}

function Mark({ india, children }: { india?: boolean; children: string }) {
  return (
    <span
      className={`rounded-full border px-[7px] text-[11px] leading-[18px] font-semibold ${
        india ? "border-ok-bd bg-ok-bg text-ok-fg" : "border-line bg-chip text-ink"
      }`}
    >
      {children}
    </span>
  );
}

/** The company's logo file if there is one, else its initials on a color picked from its slug. */
function CompanyIcon({ slug, name }: { slug: string; name: string }) {
  const logo = logoFor(slug);
  const box = "hidden h-10 w-10 shrink-0 items-center justify-center rounded-[10px] sm:flex";
  if (logo)
    return (
      <div className={`${box} border border-line bg-white p-1.5`} aria-hidden="true">
        <img src={logo} alt="" className="max-h-full max-w-full object-contain" />
      </div>
    );
  return (
    <div
      className={`${box} bg-[hsl(var(--hue)_62%_92%)] text-[13px] font-bold text-[hsl(var(--hue)_45%_30%)] dark:bg-[hsl(var(--hue)_35%_22%)] dark:text-[hsl(var(--hue)_70%_80%)]`}
      style={{ "--hue": String(companyHue(slug)) } as React.CSSProperties}
      aria-hidden="true"
    >
      {initials(name)}
    </div>
  );
}

/**
 * Eligibility (only a real result: Eligible or Check needed), closed and tag badges:
 * a right-hand column on wide cards, a row under the text on phones.
 */
function Badges({ job }: { job: Card }) {
  const shown = job.eligibility !== "pending" || job.closed || job.tag;
  if (!shown) return null;
  return (
    <div className="flex flex-wrap gap-1.5 sm:flex-col sm:items-end">
      {job.eligibility !== "pending" && <EligBadge status={job.eligibility} />}
      {job.closed && (
        <span className="rounded-full border border-line bg-chip px-2 py-px text-xs text-muted">Closed</span>
      )}
      {job.tag && <span className="rounded-full border border-line px-2 py-px text-xs">{TAG_LABEL[job.tag]}</span>}
    </div>
  );
}
