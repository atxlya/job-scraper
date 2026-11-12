import { type ReactNode, useRef, useState } from "react";

export type SwipeDir = "right" | "left";

const LOCK = 10; // px before deciding between a swipe and a scroll
const MIN = 80; // a swipe commits past this, or a third of the card, whichever is more

/**
 * Swipe a card right (Like) or left (Dismiss) with pointer events. `touch-action: pan-y`
 * leaves vertical scrolling to the browser; a drag that starts vertical never becomes a swipe.
 */
export function SwipeCard({ onSwipe, children }: { onSwipe: (dir: SwipeDir) => void; children: ReactNode }) {
  const [dx, setDx] = useState(0);
  const [settling, setSettling] = useState(false);
  const el = useRef<HTMLDivElement>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const mode = useRef<"undecided" | "swipe" | "scroll">("undecided");
  const offset = useRef(0);
  const swiped = useRef(false);

  function move(to: number) {
    offset.current = to;
    setDx(to);
  }

  function reset() {
    start.current = null;
    mode.current = "undecided";
    setSettling(true);
    move(0);
  }

  const width = () => el.current?.getBoundingClientRect().width || 0;
  const progress = Math.min(1, Math.abs(dx) / Math.max(MIN, width() / 3));

  return (
    <div className="relative overflow-hidden rounded-xl">
      {dx !== 0 && (
        <div
          aria-hidden="true"
          className={`absolute inset-0 flex items-center rounded-xl border px-5 text-sm font-bold ${
            dx > 0 ? "justify-start border-ok-bd bg-ok-bg text-ok-fg" : "justify-end border-warn-bd bg-warn-bg text-warn-fg"
          }`}
          style={{ opacity: 0.35 + 0.65 * progress }}
        >
          {dx > 0 ? "♥ Like" : "Dismiss ✕"}
        </div>
      )}
      <div
        ref={el}
        className={`relative ${settling ? "transition-transform duration-200 ease-out" : ""}`}
        style={{ transform: dx ? `translateX(${dx}px)` : undefined, touchAction: "pan-y" }}
        onTransitionEnd={() => setSettling(false)}
        onPointerDown={(e) => {
          if (e.pointerType === "mouse" && e.button !== 0) return;
          start.current = { x: e.clientX, y: e.clientY };
          mode.current = "undecided";
          swiped.current = false;
          setSettling(false);
        }}
        onPointerMove={(e) => {
          if (!start.current) return;
          const ddx = e.clientX - start.current.x;
          const ddy = e.clientY - start.current.y;
          if (mode.current === "undecided") {
            if (Math.abs(ddx) > LOCK && Math.abs(ddx) > Math.abs(ddy)) {
              mode.current = "swipe";
              e.currentTarget.setPointerCapture?.(e.pointerId);
            } else if (Math.abs(ddy) > LOCK) {
              mode.current = "scroll";
            }
          }
          if (mode.current === "swipe") move(ddx);
        }}
        onPointerUp={() => {
          if (mode.current !== "swipe") {
            start.current = null;
            return;
          }
          swiped.current = true;
          const d = offset.current;
          if (Math.abs(d) >= Math.max(MIN, width() / 3)) {
            const dir: SwipeDir = d > 0 ? "right" : "left";
            start.current = null;
            mode.current = "undecided";
            setSettling(true);
            move((d > 0 ? 1 : -1) * Math.max(width(), 400));
            setTimeout(() => {
              onSwipe(dir);
              setSettling(false);
              move(0);
            }, 180);
          } else {
            reset();
          }
        }}
        onPointerCancel={reset}
        onClickCapture={(e) => {
          // The click that ends a swipe mustn't also open the job.
          if (swiped.current) {
            e.preventDefault();
            e.stopPropagation();
            swiped.current = false;
          }
        }}
      >
        {children}
      </div>
    </div>
  );
}
