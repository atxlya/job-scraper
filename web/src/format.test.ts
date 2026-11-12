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


it("says how long since a step's date, in IST days", async () => {
  const { since, shortDay } = await import("./format");
  const now = new Date("2026-11-12T20:00:00Z"); // 01:30 on the 13th in India
  expect(since("2026-11-13", now)).toBe("today");
  expect(since("2026-11-12", now)).toBe("1 day");
  expect(since("2026-11-03", now)).toBe("10 days");
  expect(shortDay("2026-11-03")).toBe("3 Nov");
});
