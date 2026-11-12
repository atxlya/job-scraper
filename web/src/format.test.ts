import { expect, it } from "vitest";
import { companyHue, flag } from "./format";

it("turns a country code into its flag", () => {
  expect(flag("DE")).toBe("🇩🇪");
  expect(flag("in")).toBe("🇮🇳");
  expect(flag(null)).toBe("");
  expect(flag("EUR")).toBe("");
});

it("gives each company the same color every time, and different companies different ones", () => {
  expect(companyHue("google")).toBe(companyHue("google"));
  const hues = ["google", "intel", "nvidia", "qualcomm", "honeywell", "microsoft"].map(companyHue);
  expect(new Set(hues).size).toBe(hues.length);
  for (const h of hues) expect(h).toBeGreaterThanOrEqual(0), expect(h).toBeLessThan(360);
});

it("formats run durations", async () => {
  const { duration } = await import("./format");
  expect(duration(null)).toBe("—");
  expect(duration(31)).toBe("31 s");
  expect(duration(120)).toBe("2 min");
  expect(duration(91 * 60 + 20)).toBe("1 h 31 min");
});

it("says how long until a time", async () => {
  const { until } = await import("./format");
  const now = new Date("2026-11-12T16:18:00Z");
  expect(until("2026-11-12T20:30:00Z", now)).toBe("in 4 h 12 min");
  expect(until("2026-11-12T16:40:00Z", now)).toBe("in 22 min");
  expect(until("2026-11-12T16:00:00Z", now)).toBe("any minute");
});

it("shows a time in IST", async () => {
  const { clockIST } = await import("./format");
  expect(clockIST("2026-11-12T20:30:00Z")).toBe("02:00");
  expect(clockIST("2026-11-12T16:00:00Z")).toBe("21:30");
});
