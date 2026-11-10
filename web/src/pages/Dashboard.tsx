import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useState } from "react";
import { useSearchParams } from "react-router";
import { api, ApiError } from "../api";
import { FilterPanel } from "../components/FilterPanel";
import { Header } from "../components/Header";
import { JobList } from "../components/JobList";
import { StatsStrip } from "../components/StatsStrip";
import { Button } from "../components/ui";
import { activeCount, DEFAULTS, toParams, useFilters } from "../filters";
import { useMedia, WIDE } from "../hooks";
import type { JobPage } from "../types";

const PAGE = 50;

type Props = {
  /** Task 10: the selected job's detail, shown as a third column on wide screens. */
  detail?: (id: number | null) => ReactNode;
  /** Task 11: health card under the filters. */
  health?: ReactNode;
  /** Task 11: "Add company" dialog. */
  addCompany?: (open: boolean, close: () => void) => ReactNode;
};

export function Dashboard({ detail, health, addCompany }: Props) {
  const [f, set] = useFilters();
  const [params] = useSearchParams();
  const wide = useMedia(WIDE);
  const [showFilters, setShowFilters] = useState(false);
  const [adding, setAdding] = useState(false);
  const qc = useQueryClient();
  const query = toParams(f).toString();
  const selected = Number(params.get("job")) || null;

  const jobs = useInfiniteQuery({
    queryKey: ["jobs", query],
    queryFn: ({ pageParam }) =>
      api<JobPage>(`/api/jobs?${query}${query ? "&" : ""}offset=${pageParam}&limit=${PAGE}`),
    initialPageParam: 0,
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });

  const markSeen = useMutation({
    mutationFn: () =>
      api<{ marked: number }>("/api/jobs/mark-seen", {
        method: "POST",
        json: { up_to: jobs.data?.pages[0]?.loaded_at ?? new Date().toISOString() },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  const linkFor = useCallback(
    (id: number) => {
      if (!wide) return `/jobs/${id}`;
      const p = new URLSearchParams(params);
      p.set("job", String(id));
      return `/?${p.toString()}`;
    },
    [wide, params],
  );
  const onSearch = useCallback((q: string) => set({ q }), [set]);
  const n = activeCount(f);
  const error = jobs.error instanceof ApiError ? jobs.error.detail : jobs.error ? "Couldn't load jobs." : null;

  return (
    <div className="min-h-screen bg-bg">
      <Header
        q={f.q}
        onSearch={onSearch}
        onMarkAllSeen={() => markSeen.mutate()}
        markingSeen={markSeen.isPending}
        onAddCompany={addCompany ? () => setAdding(true) : undefined}
      />
      <main className="mx-auto flex max-w-[1360px] flex-col gap-5 px-4 pt-5 pb-10 lg:px-6">
        <StatsStrip />
        {!wide && (
          <Button onClick={() => setShowFilters(!showFilters)} aria-expanded={showFilters} className="self-start">
            {showFilters ? "Hide filters" : `Filters${n ? ` (${n})` : ""}`}
          </Button>
        )}
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
          {(wide || showFilters) && (
            <div className="lg:w-[240px] lg:shrink-0">
              <FilterPanel f={f} set={set}>
                {health}
              </FilterPanel>
            </div>
          )}
          <div className="min-w-0 flex-1">
            <JobList
              title={f.view === "tech" ? "Tech internships" : "All jobs"}
              pages={jobs.data}
              loading={jobs.isPending}
              error={error}
              hasMore={!!jobs.hasNextPage}
              loadingMore={jobs.isFetchingNextPage}
              onMore={() => jobs.fetchNextPage()}
              linkFor={linkFor}
              selected={selected}
              onClear={() => set({ ...DEFAULTS, view: f.view })}
            />
          </div>
          {wide && detail && <div className="min-w-0 flex-1 lg:sticky lg:top-4">{detail(selected)}</div>}
        </div>
      </main>
      {addCompany?.(adding, () => setAdding(false))}
    </div>
  );
}
