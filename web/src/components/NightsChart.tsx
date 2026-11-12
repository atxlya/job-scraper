import { useState } from "react";
import type { Night } from "../types";

const W = 140;
const H = 32;
const PAD = 4;
const BASE = H - 1; // the zero line

/** "2026-11-11" → "11 Nov" (a calendar date, no time zone involved). */
function shortDay(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? day : d.toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short" });
}

function label(n: Night): string {
  if (n.status === null) return `${shortDay(n.day)} · no full sweep`;
  if (n.status === "failed") return `${shortDay(n.day)} · failed`;
  return `${shortDay(n.day)} · ${(n.count ?? 0).toLocaleString("en-IN")} jobs${n.status === "partial" ? " (partial)" : ""}`;
}

/**
 * Jobs read by each night's full sweep, on a zero baseline so a halving looks like one.
 * A failed night is an orange dot and breaks the line; a night with no sweep is a gap.
 */
export function NightsChart({ nights }: { nights: Night[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const ran = nights.filter((n) => n.status !== null);
  if (ran.length === 0) return <span className="text-xs text-muted">No full sweep yet</span>;

  const max = Math.max(1, ...nights.map((n) => (n.status !== "failed" && n.count) || 0));
  const step = nights.length > 1 ? (W - 2 * PAD) / (nights.length - 1) : 0;
  const x = (i: number) => PAD + i * step;
  const y = (count: number) => BASE - PAD / 2 - (count / max) * (BASE - PAD * 1.5);

  // Runs of consecutive ok/partial nights become separate lines.
  const lines: string[][] = [];
  let current: string[] = [];
  let lastY = y(max / 2);
  const dots: { i: number; cy: number; failed: boolean }[] = [];
  nights.forEach((n, i) => {
    if (n.status === "ok" || n.status === "partial") {
      lastY = y(n.count ?? 0);
      current.push(`${x(i).toFixed(1)},${lastY.toFixed(1)}`);
    } else {
      if (current.length) lines.push(current);
      current = [];
      if (n.status === "failed") dots.push({ i, cy: lastY, failed: true });
    }
  });
  if (current.length) lines.push(current);
  const lastOk = nights.findLastIndex((n) => n.status === "ok" || n.status === "partial");
  if (lastOk >= 0) dots.push({ i: lastOk, cy: y(nights[lastOk].count ?? 0), failed: false });

  const summary = `Jobs read by the nightly full sweep: ${ran.map(label).map((l) => l.replace(" · ", " ").replace(" jobs", "")).join(", ")}`;

  return (
    <div className="relative inline-block">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary} className="block overflow-visible">
        <line x1={0} y1={BASE} x2={W} y2={BASE} className="stroke-line" strokeWidth={1} />
        {lines.map((pts) =>
          pts.length === 1 ? (
            <circle key={pts[0]} cx={pts[0].split(",")[0]} cy={pts[0].split(",")[1]} r={1.5} className="fill-ink/75" />
          ) : null,
        )}
        {lines.map((pts) => (
          <polyline
            key={`l${pts[0]}`}
            points={pts.join(" ")}
            fill="none"
            className="stroke-ink/75"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
        {dots.map((d) => (
          <circle
            key={`d${d.i}`}
            cx={x(d.i)}
            cy={d.cy}
            r={4}
            data-failed={d.failed ? "" : undefined}
            className={`${d.failed ? "fill-bad" : "fill-ink"} stroke-surface`}
            strokeWidth={2}
          />
        ))}
        {hover !== null && <line x1={x(hover)} y1={1} x2={x(hover)} y2={BASE} className="stroke-muted" strokeDasharray="2 2" />}
        {nights.map((n, i) => (
          <rect
            key={n.day}
            data-testid="night"
            x={x(i) - step / 2}
            y={0}
            width={Math.max(step, 8)}
            height={H}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
      </svg>
      {hover !== null && (
        <div
          role="tooltip"
          className="pointer-events-none absolute bottom-full z-10 mb-1 -translate-x-1/2 rounded-lg border border-line bg-surface px-2.5 py-1 text-xs whitespace-nowrap text-ink shadow-[0_8px_20px_rgb(0_0_0/0.15)]"
          style={{ left: x(hover) }}
        >
          {label(nights[hover])}
        </div>
      )}
    </div>
  );
}
