import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { api, ApiError } from "../api";
import { AddCompanyDialog } from "../components/AddCompanyDialog";
import { FilterPanel } from "../components/FilterPanel";
import { HealthPanel } from "../components/HealthPanel";
import { Header } from "../components/Header";
import { JobDetail } from "../components/JobDetail";
import { JobList } from "../components/JobList";
import { Kbd, ShortcutsHelp } from "../components/ShortcutsHelp";
import type { SwipeDir } from "../components/SwipeCard";
import { Toast, type ToastData } from "../components/Toast";
import { StatsStrip } from "../components/StatsStrip";
import { Button } from "../components/ui";
import { activeCount, DEFAULTS, toParams, useFilters } from "../filters";
import { todayIST } from "../format";
import { useMedia, useShortcuts, WIDE } from "../hooks";
import { type TagBody, useTagJob } from "../tagging";
import type { JobCard, JobDetail as Detail, JobPage, Tag } from "../types";

const PAGE = 50;
const HINT_KEY = "shortcuts-seen";

function hintWanted(): boolean {
  try {
    return localStorage.getItem(HINT_KEY) !== "1";
  } catch {
    return true;
  }
}

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
        // Only jobs up to the newest one when the list loaded (plan D7).
        json: { up_to_id: jobs.data?.pages[0]?.max_id ?? 0 },
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
  // On a laptop the first job opens by itself when none is picked; it isn't marked seen.
  const first = jobs.data?.pages[0]?.items[0]?.id ?? null;
  const shown = selected ?? (wide ? first : null);
  const error = jobs.error instanceof ApiError ? jobs.error.detail : jobs.error ? "Couldn't load jobs." : null;

  // --- Triage: keyboard on a laptop, swipes on a phone ---
  const items = jobs.data?.pages.flatMap((pg) => pg.items) ?? [];
  const tagJob = useTagJob();
  const [toast, setToast] = useState<ToastData | null>(null);
  const toastId = useRef(0);
  const closeToast = useCallback(() => setToast(null), []);
  const [help, setHelp] = useState(false);
  const [hint, setHint] = useState(hintWanted);

  const say = (text: string, undo?: () => void) => setToast({ id: ++toastId.current, text, undo });
  const tagOf = (id: number): Tag | null =>
    qc.getQueryData<Detail>(["job", id])?.tag ?? items.find((j) => j.id === id)?.tag ?? null;
  const save = (id: number, body: TagBody) =>
    tagJob(id, body).catch((e) => say(e instanceof ApiError ? e.detail : "Couldn't save the tag."));

  // The open job as the keys see it: `pick` moves it at once, so keys pressed before the page
  // re-renders (j j l) act on the job the last key moved to, not the one on screen.
  const cur = useRef(shown);
  const rendered = useRef(shown);
  if (rendered.current !== shown) rendered.current = cur.current = shown;
  else if (cur.current === null) cur.current = shown;

  const pick = (id: number | null) => {
    cur.current = id;
    const p = new URLSearchParams(params);
    if (id === null) p.delete("job");
    else p.set("job", String(id));
    setParams(p, { replace: true });
    if (id !== null) document.querySelector(`[data-job="${id}"]`)?.scrollIntoView({ block: "nearest" });
  };

  const step = (by: 1 | -1) => {
    const at = items.findIndex((j) => j.id === cur.current);
    const next = items[at + by];
    if (next) pick(next.id);
    else if (by === 1 && jobs.hasNextPage) jobs.fetchNextPage();
  };

  /** Dismiss with Undo. `move` goes on to the next job (keyboard); a swiped card just leaves. */
  const dismiss = (job: JobCard, move: boolean) => {
    const before = tagOf(job.id);
    if (before === "dismissed") return save(job.id, { tag: null });
    const at = items.findIndex((j) => j.id === job.id);
    const next = items[at + 1] ?? items[at - 1];
    save(job.id, { tag: "dismissed" });
    if (move && next) pick(next.id);
    say(`Dismissed · ${job.title}`, () => {
      save(job.id, { tag: before });
      if (move) pick(job.id);
    });
  };

  const current = () => items.find((j) => j.id === cur.current);
  const openHelp = () => {
    setHelp(!help);
    setHint(false);
    try {
      localStorage.setItem(HINT_KEY, "1");
    } catch {
      // storage blocked
    }
  };
  useShortcuts(
    help
      ? { Escape: () => setHelp(false), "?": () => setHelp(false) }
      : {
          j: () => step(1),
          k: () => step(-1),
          l: () => {
            const job = current();
            if (job) save(job.id, { tag: tagOf(job.id) === "liked" ? null : "liked" });
          },
          a: () => {
            const job = current();
            if (job) save(job.id, tagOf(job.id) === "applied" ? { tag: null } : { tag: "applied", event_date: todayIST() });
          },
          d: () => {
            const job = current();
            if (job) dismiss(job, true);
          },
          u: () => {
            const job = current();
            if (job) save(job.id, { tag: null });
          },
          z: () => {
            toast?.undo?.();
            closeToast();
          },
          o: () => {
            const d = cur.current ? qc.getQueryData<Detail>(["job", cur.current]) : undefined;
            if (d) window.open(d.apply_url || d.url, "_blank", "noopener,noreferrer");
          },
          "/": () => document.getElementById("q")?.focus(),
          "?": openHelp,
          Escape: () => selected && pick(null),
        },
    wide,
    (el) => el.id === "q" && el.blur(),
  );

  const onSwipe = (job: JobCard, dir: SwipeDir) => {
    if (dir === "left") return dismiss(job, false);
    const before = tagOf(job.id);
    if (before === "liked") return;
    save(job.id, { tag: "liked" });
    say(`Liked · ${job.title}`, () => save(job.id, { tag: before }));
  };

  return (
    <div className="min-h-screen bg-bg">
      <Header q={f.q} onSearch={onSearch} onAddCompany={() => setAdding(true)} />
      <main className="mx-auto flex max-w-[1360px] flex-col gap-4 px-4 pt-3 pb-10 md:pt-5 lg:gap-5 lg:px-6">
        <StatsStrip f={f} set={set} />
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-5">
          {wide && (
            <div className="w-[240px] shrink-0">
              <FilterPanel f={f} set={set}>
                <HealthPanel />
              </FilterPanel>
            </div>
          )}
          <div className="min-w-0 flex-1 lg:flex-[2_1_0%]">
            <JobList
              title={f.view === "tech" ? "Tech internships" : "All jobs"}
              pages={jobs.data}
              loading={jobs.isPending}
              error={error}
              hasMore={!!jobs.hasNextPage}
              loadingMore={jobs.isFetchingNextPage}
              onMore={() => jobs.fetchNextPage()}
              linkFor={linkFor}
              selected={shown}
              onClear={() => set({ ...DEFAULTS, view: f.view })}
              onSwipe={wide ? undefined : onSwipe}
              footer={
                wide &&
                hint && (
                  <p className="m-0 self-end text-xs text-muted">
                    Press <Kbd>?</Kbd> for shortcuts
                  </p>
                )
              }
              onMarkAllSeen={() => markSeen.mutate()}
              markingSeen={markSeen.isPending}
              aside={
                !wide && (
                  <Button
                    onClick={() => setShowFilters(!showFilters)}
                    aria-expanded={showFilters}
                    aria-controls="filters"
                    className="h-9 px-3 text-[13px]"
                  >
                    {showFilters ? "Hide filters" : `Filters${n ? ` (${n})` : ""}`}
                  </Button>
                )
              }
              panel={
                !wide &&
                showFilters && (
                  <div id="filters">
                    <FilterPanel f={f} set={set}>
                      <HealthPanel />
                    </FilterPanel>
                  </div>
                )
              }
            />
          </div>
          {wide && (
            <div className="min-w-0 flex-[3_1_0%] lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
              {shown ? (
                <JobDetail
                  id={shown}
                  picked={selected !== null}
                  onClose={
                    selected === null
                      ? undefined
                      : () => {
                          const p = new URLSearchParams(params);
                          p.delete("job");
                          setParams(p, { replace: true });
                        }
                  }
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
      {help && <ShortcutsHelp onClose={() => setHelp(false)} />}
      <Toast toast={toast} onDone={closeToast} />
    </div>
  );
}
