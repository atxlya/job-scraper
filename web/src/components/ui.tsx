import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Elig } from "../types";
import { ELIG_LABEL } from "../format";

const ELIG_CLASS: Record<Elig, string> = {
  ok: "border-ok-bd bg-ok-bg text-ok-fg",
  warn: "border-warn-bd bg-warn-bg text-warn-fg",
  pending: "border-line bg-chip text-muted",
};

export function EligBadge({ status }: { status: Elig }) {
  return (
    <span
      className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold ${ELIG_CLASS[status]}`}
    >
      {ELIG_LABEL[status]}
    </span>
  );
}

/** A filter chip: a toggle button with aria-pressed. */
export function Chip({
  on,
  children,
  ...rest
}: { on: boolean; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-pressed={on}
      className={`h-9 rounded-full border px-3 text-[13px] lg:h-8 ${
        on ? "border-ok-bd bg-ok-bg font-medium text-ok-fg" : "border-line bg-surface text-ink hover:bg-chip"
      }`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Button({
  primary,
  className = "",
  ...rest
}: { primary?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>) {
  const look = primary
    ? "border-0 bg-accent font-semibold text-on-accent hover:bg-accent-hover"
    : "border border-line bg-surface font-medium text-ink hover:bg-chip";
  return (
    <button
      type="button"
      className={`h-11 rounded-[10px] px-3.5 disabled:opacity-60 lg:h-10 ${look} ${className}`}
      {...rest}
    />
  );
}

export const card = "rounded-xl border border-line bg-surface";
export const label = "mb-2 block text-xs font-semibold uppercase tracking-wide text-muted";
