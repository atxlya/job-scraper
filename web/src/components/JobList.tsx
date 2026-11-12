import type { InfiniteData } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { JobPage } from "../types";
import type { JobCard as Card } from "../types";
import { JobCard } from "./JobCard";
import { type SwipeDir, SwipeCard } from "./SwipeCard";
import { Button } from "./ui";

type Props = {
  title: string;
  pages: InfiniteData<JobPage> | undefined;
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  loadingMore: boolean;
  onMore: () => void;
  linkFor: (id: number) => string;
  selected: number | null;
  onClear: () => void;
  onMarkAllSeen?: () => void;
  markingSeen?: boolean;
  /** /api/jobs.csv with the list's filters: the browser downloads it (streamed by the API). */
  exportHref?: string;
  /** Shown next to the title, e.g. the phone's Filters button. */
  aside?: ReactNode;
  /** Shown under the title row, e.g. the phone's filter panel. */
  panel?: ReactNode;
  /** Phones: swipe a card right to Like, left to Dismiss. */
  onSwipe?: (job: Card, dir: SwipeDir) => void;
  /** Shown under the list, e.g. the laptop's "Press ? for shortcuts". */
  footer?: ReactNode;
};

export function JobList(p: Props) {
  const items = p.pages?.pages.flatMap((pg) => pg.items) ?? [];
  const total = p.pages?.pages[0]?.total ?? 0;
  return (
    <section aria-label="Jobs" className="flex min-w-0 flex-col gap-2.5">
      <div className="flex flex-col gap-1 px-0.5">
        <div className="flex min-h-9 items-center justify-between gap-2">
          <h1 className="m-0 text-lg font-bold">{p.title}</h1>
          {p.aside}
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="text-[13px] whitespace-nowrap text-muted" aria-live="polite">
            {p.loading ? "Loading…" : `${total.toLocaleString("en-IN")} · newest first`}
          </div>
          <div className="flex items-center gap-3.5 lg:gap-2">
            {p.exportHref && total > 0 && (
              <a
                href={p.exportHref}
                download
                className="inline-flex min-h-9 items-center gap-1.5 text-[13px] font-medium text-accent no-underline hover:underline lg:h-9 lg:rounded-[10px] lg:border lg:border-line lg:bg-surface lg:px-3 lg:text-ink lg:hover:bg-chip lg:hover:no-underline"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="hidden lg:block">
                  <path d="M12 4v11" />
                  <path d="m7 10 5 5 5-5" />
                  <path d="M5 20h14" />
                </svg>
                Export CSV
              </a>
            )}
          {p.onMarkAllSeen && (
            <button
              type="button"
              onClick={p.onMarkAllSeen}
              disabled={p.markingSeen}
              className="min-h-9 text-[13px] font-medium text-accent hover:underline disabled:opacity-60 lg:h-9 lg:rounded-[10px] lg:border lg:border-line lg:bg-surface lg:px-3 lg:text-ink lg:hover:bg-chip lg:hover:no-underline"
            >
              {p.markingSeen ? "Marking…" : "Mark all as seen"}
            </button>
          )}
          </div>
        </div>
      </div>
      {p.panel}
      {p.error && (
        <p role="alert" className="rounded-lg border border-warn-bd bg-warn-bg px-3 py-2 text-[13px] text-warn-fg">
          {p.error}
        </p>
      )}
      {!p.loading && !p.error && items.length === 0 && (
        <div className="rounded-xl border border-dashed border-line px-4 py-10 text-center text-muted">
          <p className="m-0 mb-3">No jobs match these filters.</p>
          <Button onClick={p.onClear}>Clear filters</Button>
        </div>
      )}
      {items.map((j) => {
        const c = <JobCard key={j.id} job={j} to={p.linkFor(j.id)} selected={p.selected === j.id} />;
        const onSwipe = p.onSwipe;
        return onSwipe ? (
          <SwipeCard key={j.id} onSwipe={(dir) => onSwipe(j, dir)}>
            {c}
          </SwipeCard>
        ) : (
          c
        );
      })}
      {items.length > 0 && (
        <div className="p-2 text-center text-[13px] text-muted">
          Showing {items.length.toLocaleString("en-IN")} of {total.toLocaleString("en-IN")}
          {p.hasMore && (
            <>
              {" · "}
              <button type="button" className="text-accent hover:underline" onClick={p.onMore} disabled={p.loadingMore}>
                {p.loadingMore ? "Loading…" : "Load more"}
              </button>
            </>
          )}
        </div>
      )}
      {p.footer}
    </section>
  );
}
