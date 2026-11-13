import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, ApiError } from "../api";
import type { Schedule } from "../types";
import { Button, card } from "./ui";

type Body = Pick<Schedule, "incremental_minutes" | "full_at" | "tracked_at">;

const field = "h-10 rounded-[10px] border border-line bg-surface px-3 text-[13px] text-ink";

/** When the worker scrapes. Saved on the server; the worker picks a change up within a minute. */
export function ScheduleCard() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["schedule"], queryFn: () => api<Schedule>("/api/schedule") });
  const [form, setForm] = useState<Body | null>(null);
  const [saved, setSaved] = useState(false);
  const save = useMutation({
    mutationFn: (json: Body) => api<Schedule>("/api/schedule", { method: "PUT", json }),
    onSuccess: (s) => {
      qc.setQueryData(["schedule"], s);
      setForm(null);
      setSaved(true);
    },
  });
  if (!data) return null;

  function edit() {
    if (!data) return;
    save.reset();
    setSaved(false);
    setForm({ incremental_minutes: data.incremental_minutes, full_at: data.full_at, tracked_at: data.tracked_at });
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (form) save.mutate(form);
  }

  return (
    <section aria-label="Schedule" className={`${card} flex flex-col gap-2 px-4 py-3`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p data-testid="schedule" className="m-0 text-[13px] text-muted">
          <strong className="text-ink">Schedule</strong> · Quick check every {data.incremental_minutes} min · Full sweep{" "}
          {data.full_at} IST · Re-check tracked jobs {data.tracked_at} IST
        </p>
        {!form && (
          <Button aria-label="Edit schedule" onClick={edit}>
            Edit
          </Button>
        )}
      </div>
      {saved && !form && (
        <p role="status" className="m-0 text-[13px] text-ok-fg">
          Saved. The worker switches within a minute.
        </p>
      )}
      {form && (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs font-semibold text-muted">
            Quick check every (minutes)
            <input
              type="number"
              required
              className={`${field} w-28`}
              value={Number.isNaN(form.incremental_minutes) ? "" : form.incremental_minutes}
              onChange={(e) => setForm({ ...form, incremental_minutes: e.target.valueAsNumber })}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-semibold text-muted">
            Full sweep at (IST)
            <input
              type="time"
              required
              className={field}
              value={form.full_at}
              onChange={(e) => setForm({ ...form, full_at: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-semibold text-muted">
            Re-check tracked jobs at (IST)
            <input
              type="time"
              required
              className={field}
              value={form.tracked_at}
              onChange={(e) => setForm({ ...form, tracked_at: e.target.value })}
            />
          </label>
          <div className="flex gap-2">
            <Button primary type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
            <Button onClick={() => setForm(null)}>Cancel</Button>
          </div>
          {save.error && (
            <p role="alert" className="m-0 basis-full text-[13px] text-warn-fg">
              {save.error instanceof ApiError ? save.error.detail : "Couldn't save the schedule."}
            </p>
          )}
          <p className="m-0 basis-full text-xs text-muted">
            15–360 minutes. The full sweep and the re-check must be at least an hour apart.
          </p>
        </form>
      )}
    </section>
  );
}
