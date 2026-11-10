import { useEffect, useState } from "react";

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
