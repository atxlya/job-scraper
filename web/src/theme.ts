import { useEffect, useSyncExternalStore } from "react";

export type ThemeMode = "system" | "light" | "dark";
const KEY = "theme";
const listeners = new Set<() => void>();

function read(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    // storage blocked
  }
  return "system";
}

let current: ThemeMode = read();

function systemDark(): boolean {
  return !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

function apply() {
  const dark = current === "dark" || (current === "system" && systemDark());
  document.documentElement.classList.toggle("dark", dark);
}

export function setTheme(mode: ThemeMode) {
  current = mode;
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    // storage blocked
  }
  apply();
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** One shared theme setting: system / light / dark, remembered in this browser (plan D13). */
export function useTheme(): [ThemeMode, (m: ThemeMode) => void] {
  const mode = useSyncExternalStore(subscribe, () => current);
  useEffect(() => {
    apply();
    if (!window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  return [mode, setTheme];
}
