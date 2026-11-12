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
