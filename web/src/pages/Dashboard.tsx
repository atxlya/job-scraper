import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useSearchParams } from "react-router";
import { api, ApiError } from "../api";
import { AddCompanyDialog } from "../components/AddCompanyDialog";
import { FilterPanel } from "../components/FilterPanel";
import { HealthPanel } from "../components/HealthPanel";
import { Header } from "../components/Header";
import { JobDetail } from "../components/JobDetail";
import { JobList } from "../components/JobList";
import { StatsStrip } from "../components/StatsStrip";
import { Button } from "../components/ui";
import { activeCount, DEFAULTS, toParams, useFilters } from "../filters";
import { useMedia, WIDE } from "../hooks";
import type { JobPage } from "../types";

const PAGE = 50;

export function Dashboard() {
  const [f, set] = useFilters();
  const [params, setParams] = useSearchParams();
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
        onAddCompany={() => setAdding(true)}
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
                <HealthPanel />
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
          {wide && (
            <div className="min-w-0 flex-1 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
              {selected ? (
                <JobDetail
                  id={selected}
                  onClose={() => {
                    const p = new URLSearchParams(params);
                    p.delete("job");
                    setParams(p, { replace: true });
                  }}
                />
              ) : (
                <div className="rounded-xl border border-dashed border-line px-6 py-16 text-center text-muted">
                  Pick a job to see its details here.
                </div>
              )}
            </div>
          )}
        </div>
      </main>
      <AddCompanyDialog open={adding} onClose={() => setAdding(false)} />
    </div>
  );
}
