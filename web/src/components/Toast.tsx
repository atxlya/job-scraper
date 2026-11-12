import { useEffect } from "react";

export type ToastData = { id: number; text: string; undo?: () => void };

export const TOAST_MS = 5000;

/** A short message at the bottom of the screen, with Undo when there is one. Gone after 5 s. */
export function Toast({ toast, onDone }: { toast: ToastData | null; onDone: () => void }) {
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(onDone, TOAST_MS);
    return () => clearTimeout(t);
  }, [toast, onDone]);
  if (!toast) return null;
  return (
    <div
      role="status"
      className="fixed inset-x-4 bottom-4 z-30 mx-auto flex max-w-sm items-center justify-between gap-3 overflow-hidden rounded-xl bg-ink px-4 py-3 text-[14px] text-bg shadow-[0_10px_30px_rgb(0_0_0/0.3)] lg:right-6 lg:left-auto lg:mx-0"
    >
      <span className="min-w-0 truncate">{toast.text}</span>
      {toast.undo && (
        <button
          type="button"
          className="shrink-0 rounded-md px-2 py-1 text-[13px] font-bold tracking-wide text-accent uppercase hover:bg-white/10"
          onClick={() => {
            toast.undo?.();
            onDone();
          }}
        >
          Undo
        </button>
      )}
      <span
        key={toast.id}
        aria-hidden="true"
        className="toast-timer absolute bottom-0 left-0 h-0.5 bg-accent"
        style={{ animationDuration: `${TOAST_MS}ms` }}
      />
    </div>
  );
}
