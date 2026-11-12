import { useEffect, useRef } from "react";

const GROUPS: [string, [string[], string][]][] = [
  [
    "Move",
    [
      [["j", "k"], "Next / previous job"],
      [["o"], "Open the apply link in a new tab"],
    ],
  ],
  [
    "Tag the open job",
    [
      [["l"], "Like (again to remove)"],
      [["a"], "Applied, dated today (again to remove)"],
      [["d"], "Dismiss and go to the next job"],
      [["u"], "Remove the tag"],
      [["z"], "Undo the last swipe or dismiss"],
    ],
  ],
  [
    "Other",
    [
      [["/"], "Search"],
      [["Esc"], "Leave search, or close the job"],
      [["?"], "This list"],
    ],
  ],
];

export function Kbd({ children }: { children: string }) {
  return (
    <kbd className="inline-block min-w-[22px] rounded-md border border-b-2 border-line bg-chip px-1.5 text-center font-mono text-xs font-semibold text-ink">
      {children}
    </kbd>
  );
}

/** The ? overlay. Esc, ? or a click outside closes it. */
export function ShortcutsHelp({ onClose }: { onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => box.current?.focus(), []);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/45 p-4" onClick={onClose}>
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        tabIndex={-1}
        className="w-full max-w-[420px] rounded-2xl border border-line bg-surface px-5 py-4 text-ink shadow-[0_20px_50px_rgb(0_0_0/0.3)] outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-2.5 flex items-baseline justify-between">
          <h2 id="shortcuts-title" className="m-0 text-base font-semibold">
            Keyboard shortcuts
          </h2>
          <span className="text-[13px] text-muted">Esc to close</span>
        </div>
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-3.5 gap-y-1.5 text-[13px]">
          {GROUPS.map(([group, keys]) => (
            <div key={group} className="contents">
              <div className="col-span-2 mt-1.5 text-[11px] font-semibold tracking-wide text-muted uppercase">{group}</div>
              {keys.map(([ks, what]) => (
                <div key={what} className="contents">
                  <dt className="flex gap-1">
                    {ks.map((k) => (
                      <Kbd key={k}>{k}</Kbd>
                    ))}
                  </dt>
                  <dd className="m-0">{what}</dd>
                </div>
              ))}
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
