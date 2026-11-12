import { useEffect, useRef, useState } from "react";

/** True while the media query matches, e.g. useMedia("(min-width: 1024px)"). */
export function useMedia(query: string): boolean {
  const get = () => (typeof window !== "undefined" && window.matchMedia?.(query).matches) || false;
  const [matches, setMatches] = useState(get);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const on = () => setMatches(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return matches;
}

export const WIDE = "(min-width: 1024px)";

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

/**
 * Single-key shortcuts, keyed by KeyboardEvent.key. Ignored while typing in a field and with
 * Ctrl, Cmd or Alt held; Escape still reaches `onEscapeInField` so it can leave the search box.
 */
export function useShortcuts(
  keys: Record<string, () => void>,
  enabled: boolean,
  onEscapeInField?: (el: HTMLElement) => void,
) {
  // Always the latest handlers, without re-adding the listener on every render.
  const latest = useRef({ keys, onEscapeInField });
  latest.current = { keys, onEscapeInField };
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
      if (typing(e.target)) {
        if (e.key === "Escape") latest.current.onEscapeInField?.(e.target as HTMLElement);
        return;
      }
      const run = latest.current.keys[e.key];
      if (!run) return;
      e.preventDefault();
      run();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
