import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import type { AddResult, Detected } from "../types";
import { Button } from "./ui";

const DETECT_DELAY_MS = 400;
const input = "h-11 w-full rounded-lg border border-line bg-surface px-3 text-ink lg:h-10";

export function describe(d: Detected): string {
  const c = d.config as Record<string, string>;
  if (d.adapter === "workday") return `Workday · tenant ${c.tenant} · site ${c.site}`;
  if (d.adapter === "oracle_hcm") return `Oracle HCM · ${c.host} · site ${c.site}`;
  if (d.adapter === "eightfold") return `Eightfold · ${c.host}`;
  return d.adapter;
}

function titleCase(s: string): string {
  return s.replace(/[-_]+/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

/** Paste a careers URL; the server detects the platform, test-fetches, and saves only on success (§3). */
export function AddCompanyDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [detected, setDetected] = useState<Detected | null>(null);
  const [detectError, setDetectError] = useState<string | null>(null);

  const add = useMutation({
    mutationFn: () =>
      api<AddResult>("/api/sources", { method: "POST", json: { company_name: name.trim(), url: url.trim() } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["filters"] });
    },
  });

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    // Older browsers and jsdom lack showModal(); the open attribute is the fallback.
    if (open && !d.open) {
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
    }
    if (!open && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
  }, [open]);

  useEffect(() => {
    setDetected(null);
    setDetectError(null);
    const u = url.trim();
    if (!u) return;
    let stale = false;
    const t = setTimeout(async () => {
      try {
        const d = await api<Detected>("/api/sources/detect", { method: "POST", json: { url: u } });
        if (stale) return;
        setDetected(d);
        // Workday tenants and Eightfold subdomains are usually the company; Oracle hosts aren't.
        if (d.adapter !== "oracle_hcm") setName((n) => n || titleCase(d.key_hint));
      } catch (e) {
        if (!stale) setDetectError(e instanceof ApiError ? e.detail : "Couldn't check that URL.");
      }
    }, DETECT_DELAY_MS);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [url]);

  function close() {
    setName("");
    setUrl("");
    add.reset();
    onClose();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (detected && name.trim()) add.mutate();
  }

  const done = add.data;
  return (
    <dialog
      ref={ref}
      onClose={close}
      aria-labelledby="add-company-title"
      className="m-auto w-[min(520px,calc(100vw-32px))] rounded-xl border border-line bg-surface p-0 text-ink backdrop:bg-black/40"
    >
      <form onSubmit={submit} className="flex flex-col gap-4 p-5">
        <h2 id="add-company-title" className="m-0 text-lg font-bold">
          Add company
        </h2>
        {done ? (
          <div className="flex flex-col gap-2" role="status">
            <p className="m-0 font-semibold">Added — {done.jobs_found} jobs found</p>
            <p className="m-0 text-[13px] text-muted">
              The first run stores its jobs quietly, then new internships are alerted as usual.
            </p>
            <ul className="m-0 list-disc pl-5 text-[13px]">
              {done.sample_titles.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </div>
        ) : (
          <>
            <div>
              <label htmlFor="add-url" className="mb-1.5 block text-[13px] font-semibold">
                Careers page URL
              </label>
              <input
                id="add-url"
                type="url"
                required
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://company.wd1.myworkdayjobs.com/Careers"
                className={input}
              />
              <p className="mt-1.5 mb-0 min-h-5 text-[13px]" aria-live="polite">
                {detected ? (
                  <span className="text-ok-fg">{describe(detected)}</span>
                ) : detectError ? (
                  <span className="text-warn-fg">{detectError}</span>
                ) : (
                  <span className="text-muted">Workday, Eightfold and Oracle HCM sites are supported.</span>
                )}
              </p>
            </div>
            <div>
              <label htmlFor="add-name" className="mb-1.5 block text-[13px] font-semibold">
                Company name
              </label>
              <input id="add-name" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} className={input} />
            </div>
            {add.error && (
              <p role="alert" className="m-0 rounded-lg border border-warn-bd bg-warn-bg px-3 py-2 text-[13px] text-warn-fg">
                {add.error instanceof ApiError ? add.error.detail : "Couldn't add the company."}
              </p>
            )}
          </>
        )}
        <div className="flex justify-end gap-2">
          {done ? (
            <Button primary onClick={close}>
              Done
            </Button>
          ) : (
            <>
              <Button onClick={close}>Cancel</Button>
              <Button primary type="submit" disabled={!detected || !name.trim() || add.isPending}>
                {add.isPending ? "Testing…" : "Test and add"}
              </Button>
            </>
          )}
        </div>
      </form>
    </dialog>
  );
}
