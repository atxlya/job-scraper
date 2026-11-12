import { afterEach, beforeEach, expect, it, vi } from "vitest";

function metas() {
  document.head.innerHTML =
    '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">' +
    '<meta name="theme-color" content="#171a21" media="(prefers-color-scheme: dark)">';
}
const colors = () => [...document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')].map((m) => m.content);

beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
});
afterEach(() => vi.unstubAllGlobals());

it("the phone's status bar follows a theme picked in the app, and the system again after", async () => {
  metas();
  const { setTheme } = await import("./theme");
  setTheme("dark");
  expect(colors()).toEqual(["#171a21", "#171a21"]);
  setTheme("light");
  expect(colors()).toEqual(["#ffffff", "#ffffff"]);
  setTheme("system");
  expect(colors()).toEqual(["#ffffff", "#171a21"]);
});
