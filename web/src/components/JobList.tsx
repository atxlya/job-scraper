import type { InfiniteData } from "@tanstack/react-query";
import type { JobPage } from "../types";
import { JobCard } from "./JobCard";
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
};

export function JobList(p: Props) {
  const items = p.pages?.pages.flatMap((pg) => pg.items) ?? [];
  const total = p.pages?.pages[0]?.total ?? 0;
  return (
    <section aria-label="Jobs" className="flex min-w-0 flex-col gap-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-0.5">
        <h1 className="m-0 text-lg font-bold">{p.title}</h1>
        <div className="text-[13px] text-muted" aria-live="polite">
          {p.loading ? "Loading…" : `${total.toLocaleString("en-IN")} · newest first`}
        </div>
      </div>
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
      {items.map((j) => (
        <JobCard key={j.id} job={j} to={p.linkFor(j.id)} selected={p.selected === j.id} />
      ))}
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
    </section>
  );
}
