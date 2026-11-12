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
export const STAGE_LABEL = { applied: "Applied", oa: "OA", interview: "Interview", offer: "Offer", rejected: "Rejected" } as const;

/** "3 Nov" from a YYYY-MM-DD date. */
export function shortDay(ymd: string): string {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short" });
}

/** Whole days from a YYYY-MM-DD date to today in IST: "today", "1 day", "10 days". */
export function since(ymd: string, now: Date = new Date()): string {
  const [ty, tm, td] = todayIST(now).split("-").map(Number);
  const [y, m, d] = ymd.split("-").map(Number);
  const days = Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(y, m - 1, d)) / 86_400_000);
  if (days <= 0) return "today";
  return days === 1 ? "1 day" : `${days} days`;
}

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

/** A run's length: "31 s", "2 min", "1 h 31 min". */
export function duration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const min = Math.round(seconds / 60);
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h${min % 60 ? ` ${min % 60} min` : ""}`;
}

/** "in 4 h 12 min" until a future time. */
export function until(iso: string, now: Date = new Date()): string {
  const s = (new Date(iso).getTime() - now.getTime()) / 1000;
  return s < 60 ? "any minute" : `in ${duration(s)}`;
}

/** "02:00": a time of day in IST. */
export function clockIST(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { timeZone: IST, hour: "2-digit", minute: "2-digit" });
}

/** "12 Nov, 21:30" in IST. */
export function dayTimeIST(iso: string): string {
  return `${new Date(iso).toLocaleDateString("en-GB", { timeZone: IST, day: "numeric", month: "short" })}, ${clockIST(iso)}`;
}
