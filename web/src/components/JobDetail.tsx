import { type InfiniteData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { day, TAG_LABEL, todayIST } from "../format";
import type { JobDetail as Detail, JobPage, Sections, Tag } from "../types";
import { Button, card } from "./ui";

const HEAD = {
  ok: "Eligible — nothing in the posting rules you out",
  warn: "Check needed — the posting has a restriction",
  pending: "Eligibility not checked yet",
} as const;

const BOX = {
  ok: "border-ok-bd bg-ok-bg text-ok-fg",
  warn: "border-warn-bd bg-warn-bg text-warn-fg",
  pending: "border-line bg-chip text-ink",
} as const;

const NOTE_DELAY_MS = 800;

function errorText(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.detail : fallback;
}

export function JobDetail({ id, onClose }: { id: number; onClose?: () => void }) {
  const qc = useQueryClient();
  const key = ["job", id];
  const { data: job, error } = useQuery({
    queryKey: key,
    queryFn: () => api<Detail>(`/api/jobs/${id}`),
  });

  // Opening a job marks it seen, and clears its NEW badge in the list without a refetch.
  const seenFor = useRef<number | null>(null);
  useEffect(() => {
    if (seenFor.current === id) return;
    seenFor.current = id;
    api(`/api/jobs/${id}/seen`, { method: "POST" })
      .then(() => {
        qc.setQueriesData<InfiniteData<JobPage>>({ queryKey: ["jobs"] }, (old) =>
          old
            ? {
                ...old,
                pages: old.pages.map((p) => ({
                  ...p,
                  items: p.items.map((j) => (j.id === id ? { ...j, is_new: false } : j)),
                })),
              }
            : old,
        );
      })
      .catch(() => undefined);
  }, [id, qc]);

  // A job stored without a description fetches it once when opened (plan D8).
  const fetchDesc = useMutation({
    mutationFn: () => api<Detail>(`/api/jobs/${id}/description`, { method: "POST" }),
    onSuccess: (d) => qc.setQueryData(key, d),
  });
  const fetchedFor = useRef<number | null>(null);
  useEffect(() => {
    if (!job || job.has_description || job.closed || fetchedFor.current === id) return;
    fetchedFor.current = id;
    fetchDesc.mutate();
  }, [job, id, fetchDesc]);

  const tag = useMutation({
    mutationFn: (body: { tag: Tag | null; event_date?: string; note?: string }) =>
      api<Detail>(`/api/jobs/${id}/tag`, { method: "PUT", json: body }),
    onSuccess: (d) => {
      qc.setQueryData(key, d);
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  if (error) {
    return (
      <article className={`${card} p-6`} role="alert">
        {errorText(error, "Couldn't load this job.")}
      </article>
    );
  }
  if (!job) {
    return <article className={`${card} p-6 text-muted`}>Loading…</article>;
  }

  const setTag = (t: Tag) => tag.mutate({ tag: job.tag === t ? null : t });

  return (
    <article aria-label="Job details" className={`${card} flex flex-col gap-4 p-5 lg:p-[22px]`}>
      <div>
        <div className="flex items-start justify-between gap-2">
          <div className="text-[13px] font-medium text-muted">
            {job.company} · {job.external_id}
          </div>
          {onClose && (
            <button type="button" onClick={onClose} aria-label="Close job details" className="-m-2 h-11 w-11 rounded-lg text-muted hover:bg-chip">
              ×
            </button>
          )}
        </div>
        <h2 className="mt-1 mb-1.5 text-xl leading-tight font-semibold">{job.title}</h2>
        <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-[13px] text-muted">
          {job.locations.length > 0 && <span>{job.locations.join(" · ")}</span>}
          {job.employment_type && <span>{job.employment_type}</span>}
          {job.posted_at && <span>Posted {day(job.posted_at)}</span>}
          <span>First seen {day(job.first_seen_at)}</span>
          {job.closed && <span className="font-semibold text-warn-fg">Closed</span>}
        </div>
      </div>

      <EligibilityBox job={job} />

      <div className="flex flex-wrap gap-2">
        <a
          href={job.apply_url || job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-11 items-center gap-1.5 rounded-[10px] bg-accent px-4 font-semibold text-on-accent no-underline hover:bg-accent-hover lg:h-10"
        >
          Apply on {job.company}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M7 17 17 7" />
            <path d="M8 7h9v9" />
          </svg>
        </a>
        {job.apply_url && job.apply_url !== job.url && (
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-11 items-center rounded-[10px] border border-line px-3.5 font-medium text-ink no-underline hover:bg-chip lg:h-10"
          >
            Original posting
          </a>
        )}
        <TagButton on={job.tag === "liked"} onClick={() => setTag("liked")} disabled={tag.isPending}>
          Like
        </TagButton>
        <AppliedButton job={job} busy={tag.isPending} onSave={(b) => tag.mutate(b)} />
        <TagButton on={job.tag === "dismissed"} onClick={() => setTag("dismissed")} disabled={tag.isPending}>
          Dismiss
        </TagButton>
      </div>
      {tag.error && <p role="alert" className="text-[13px] text-warn-fg">{errorText(tag.error, "Couldn't save the tag.")}</p>}

      <Body job={job} fetching={fetchDesc.isPending} fetchError={fetchDesc.error} />

      <NoteBox key={job.id} id={job.id} initial={job.note ?? ""} />

      <History job={job} />
    </article>
  );
}

function TagButton({ on, ...rest }: { on: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-pressed={on}
      className={`h-11 rounded-[10px] border px-3.5 font-medium disabled:opacity-60 lg:h-10 ${
        on ? "border-accent bg-ok-bg text-ok-fg" : "border-line bg-surface text-ink hover:bg-chip"
      }`}
      {...rest}
    />
  );
}

function AppliedButton({
  job,
  busy,
  onSave,
}: {
  job: Detail;
  busy: boolean;
  onSave: (b: { tag: Tag | null; event_date?: string; note?: string }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(todayIST());
  const [note, setNote] = useState("");
  const on = job.tag === "applied";

  function save(e: FormEvent) {
    e.preventDefault();
    onSave({ tag: "applied", event_date: date, note: note.trim() || undefined });
    setOpen(false);
    setNote("");
  }

  return (
    <>
      <TagButton on={on} disabled={busy} aria-expanded={on ? undefined : open} onClick={() => (on ? onSave({ tag: null }) : setOpen(!open))}>
        Applied
      </TagButton>
      {open && !on && (
        <form onSubmit={save} className="flex w-full flex-wrap items-end gap-2 rounded-lg border border-line bg-bg p-3">
          <div>
            <label htmlFor={`applied-on-${job.id}`} className="mb-1 block text-xs font-semibold text-muted">
              Applied on
            </label>
            <input
              id={`applied-on-${job.id}`}
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="h-11 rounded-lg border border-line bg-surface px-2 text-ink lg:h-10"
            />
          </div>
          <div className="min-w-[160px] flex-1">
            <label htmlFor={`applied-note-${job.id}`} className="mb-1 block text-xs font-semibold text-muted">
              Note (optional)
            </label>
            <input
              id={`applied-note-${job.id}`}
              value={note}
              maxLength={2000}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. via referral"
              className="h-11 w-full rounded-lg border border-line bg-surface px-2 text-ink lg:h-10"
            />
          </div>
          <Button primary type="submit">
            Save
          </Button>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
        </form>
      )}
    </>
  );
}

function EligibilityBox({ job }: { job: Detail }) {
  let note = "Checked by Gemini for a Bachelor's student based in India.";
  if (job.eligibility !== "ok") {
    if (job.unclear) note = "Gemini couldn't tell — read the posting.";
    else if (job.checking) note = "Gemini will read the posting soon — this updates automatically.";
    else if (!job.tech_internship) note = "Eligibility is only checked for tech internships.";
    else if (!job.quote) note = job.degree ? "From the job title." : "Not checked yet.";
    else note = "Quoted from the posting. You decide.";
  }
  return (
    <div className={`rounded-xl border px-3.5 py-3 ${BOX[job.eligibility]}`}>
      <div className="font-semibold">{HEAD[job.eligibility]}</div>
      {job.degree && <div className="mt-1.5 text-[13px]">⚠ <span>For {job.degree} students only (from the title)</span></div>}
      {job.quote && <div className="mt-1.5 text-[13px] italic">{`“${job.quote}”`}</div>}
      <div className="mt-1 text-xs opacity-85">{note}</div>
    </div>
  );
}

const SECTION_ORDER: [keyof Sections, string][] = [
  ["about", "About"],
  ["responsibilities", "Responsibilities"],
  ["requirements", "Requirements"],
  ["preferred", "Preferred"],
  ["eligibility", "Eligibility"],
];

function Body({ job, fetching, fetchError }: { job: Detail; fetching: boolean; fetchError: unknown }) {
  const h3 = "m-0 mb-1 text-[13px] font-semibold uppercase tracking-wide text-muted";
  if (job.sections) {
    return (
      <div className="flex flex-col gap-3.5">
        {SECTION_ORDER.map(([k, title]) => {
          const v = job.sections?.[k];
          if (!v || (Array.isArray(v) && v.length === 0)) return null;
          return (
            <section key={k}>
              <h3 className={h3}>{title}</h3>
              {Array.isArray(v) ? (
                <ul className="m-0 list-disc pl-[18px]">
                  {v.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              ) : (
                <p className="m-0">{v}</p>
              )}
            </section>
          );
        })}
      </div>
    );
  }
  if (job.description_html) {
    // Sanitised on the server with nh3 (plan D9).
    return <div className="prose-posting" dangerouslySetInnerHTML={{ __html: job.description_html }} />;
  }
  if (fetching) return <p className="m-0 text-muted">Fetching the description from {job.company}…</p>;
  if (fetchError)
    return (
      <p role="alert" className="m-0 rounded-lg border border-warn-bd bg-warn-bg px-3 py-2 text-[13px] text-warn-fg">
        {errorText(fetchError, "Couldn't fetch the description.")} Open the original posting to read it.
      </p>
    );
  return <p className="m-0 text-muted">No description stored for this job.</p>;
}

function NoteBox({ id, initial }: { id: number; initial: string }) {
  const [text, setText] = useState(initial);
  const [status, setStatus] = useState<"" | "saving" | "saved" | "error">("");
  const saved = useRef(initial);
  const latest = useRef(initial);
  latest.current = text;

  // Leaving the job (another card, closing the panel) before the debounce fires
  // still saves what was typed. keepalive lets the request outlive the page.
  useEffect(
    () => () => {
      if (latest.current !== saved.current) {
        api(`/api/jobs/${id}/note`, {
          method: "PUT",
          json: { note: latest.current },
          keepalive: true,
        }).catch(() => undefined);
      }
    },
    [id],
  );

  useEffect(() => {
    if (text === saved.current) return;
    const t = setTimeout(async () => {
      setStatus("saving");
      try {
        await api(`/api/jobs/${id}/note`, { method: "PUT", json: { note: text } });
        saved.current = text;
        setStatus("saved");
      } catch {
        setStatus("error");
      }
    }, NOTE_DELAY_MS);
    return () => clearTimeout(t);
  }, [text, id]);

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <label htmlFor={`note-${id}`} className="text-[13px] font-semibold">
          Note
        </label>
        <span className="text-xs text-muted" aria-live="polite">
          {status === "saving" ? "Saving…" : status === "saved" ? "Saved" : status === "error" ? "Couldn't save" : ""}
        </span>
      </div>
      <textarea
        id={`note-${id}`}
        rows={2}
        maxLength={5000}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="e.g. OA link came by email on 14 Dec"
        className="w-full resize-y rounded-lg border border-line bg-surface px-2.5 py-2 text-ink"
      />
    </div>
  );
}

const FIELD = {
  description: "Description changed",
  title: "Title changed",
  locations: "Locations changed",
  apply_url: "Apply link changed",
  employment_type: "Job type changed",
  posted_at: "Posted date changed",
} as Record<string, string>;

function History({ job }: { job: Detail }) {
  const events = [
    ...job.tag_history.map((e) => ({
      at: e.at,
      text: e.to_tag
        ? `${TAG_LABEL[e.to_tag]}${e.event_date ? ` (${day(e.event_date)})` : ""}${e.note ? ` — ${e.note}` : ""}`
        : `Removed ${e.from_tag ? TAG_LABEL[e.from_tag] : "tag"}`,
    })),
    ...job.changes.map((c) => ({ at: c.at, text: c.fields.map((f) => FIELD[f] ?? `${f} changed`).join(", ") })),
  ].sort((a, b) => b.at.localeCompare(a.at));
  return (
    <div className="border-t border-line pt-2.5 text-xs text-muted">
      {events.length === 0 ? (
        <span>First seen {day(job.first_seen_at)} · no changes since</span>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {events.map((e, i) => (
            <li key={i}>
              {day(e.at)} · {e.text}
            </li>
          ))}
          <li>First seen {day(job.first_seen_at)}</li>
        </ul>
      )}
    </div>
  );
}
