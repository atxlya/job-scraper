const IST = "Asia/Kolkata";

/** "just now", "5m ago", "2h ago", "3d ago", then a date. */
export function ago(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "";
  const s = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 30 * 86400) return `${Math.floor(s / 86400)}d ago`;
  return day(iso);
}

/** "12 Nov 2026" in IST. */
export function day(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-IN", {
    timeZone: IST,
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Today's date in IST as YYYY-MM-DD (for date inputs). */
export function todayIST(now: Date = new Date()): string {
  return now.toLocaleDateString("en-CA", { timeZone: IST });
}

export function initials(company: string): string {
  const words = company.split(/[\s&.-]+/).filter(Boolean);
  if (words.length > 1) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0]?.[0] ?? "?").toUpperCase();
}

export const ELIG_LABEL = { ok: "Eligible", warn: "Check needed", pending: "Not checked" } as const;
export const TAG_LABEL = { liked: "Liked", applied: "Applied", dismissed: "Dismissed" } as const;

/** "DE" → 🇩🇪 (regional indicator letters). Windows shows the two letters instead. */
export function flag(code: string | null): string {
  if (!code || !/^[a-z]{2}$/i.test(code)) return "";
  return [...code.toUpperCase()].map((c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0))).join("");
}

/** A hue (0–359) that is always the same for a company, so its icon keeps its color. */
export function companyHue(slug: string): number {
  let h = 2166136261; // FNV-1a
  for (const ch of slug) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) % 360;
}
