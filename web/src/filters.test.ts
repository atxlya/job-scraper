import { describe, expect, it } from "vitest";
import { activeCount, DEFAULTS, type Filters, fromParams, isPreset, PRESETS, toParams } from "./filters";

const sets: Filters[] = [
  DEFAULTS,
  { ...DEFAULTS, view: "all", company: ["google", "nvidia"], loc: "india", q: "ml" },
  { ...DEFAULTS, elig: ["ok", "warn"], posted: "7d", tag: ["liked", "untagged"], dismissed: true },
  { ...DEFAULTS, newToday: true },
];

describe("filters", () => {
  it.each(sets)("round-trips through the URL", (f) => {
    expect(fromParams(toParams(f))).toEqual(f);
  });

  it("defaults make an empty query string", () => {
    expect(toParams(DEFAULTS).toString()).toBe("");
  });

  it("uses the API's parameter names, repeated for lists", () => {
    expect(toParams({ ...DEFAULTS, company: ["a", "b"], dismissed: true }).toString()).toBe(
      "company=a&company=b&dismissed=true",
    );
  });

  it("ignores bad values and unrelated params", () => {
    const f = fromParams(
      new URLSearchParams("elig=bogus&elig=ok&posted=9y&view=x&loc=india;drop&job=5&tag=nope"),
    );
    expect(f).toEqual({ ...DEFAULTS, elig: ["ok"] });
  });

  it("accepts a two-letter country", () => {
    expect(fromParams(new URLSearchParams("loc=GB")).loc).toBe("GB");
  });

  it("writes new=today, the API's name for the New today filter", () => {
    expect(toParams({ ...DEFAULTS, newToday: true }).toString()).toBe("new=today");
    expect(fromParams(new URLSearchParams("new=yes")).newToday).toBe(false);
  });

  it("each stat preset is a whole filter set, so the list matches the tile's number", () => {
    expect(toParams(PRESETS.open).toString()).toBe("");
    expect(toParams(PRESETS.new).toString()).toBe("new=today");
    expect(toParams(PRESETS.liked).toString()).toBe("view=all&tag=liked");
    expect(toParams(PRESETS.applied).toString()).toBe("view=all&tag=applied");
  });

  it("a preset is active only while the filters match it exactly", () => {
    expect(isPreset(DEFAULTS, PRESETS.open)).toBe(true);
    expect(isPreset({ ...PRESETS.liked }, PRESETS.liked)).toBe(true);
    expect(isPreset({ ...PRESETS.liked, company: ["google"] }, PRESETS.liked)).toBe(false);
    expect(isPreset({ ...DEFAULTS, q: "ml" }, PRESETS.open)).toBe(false);
  });
});

it("keeps known categories from the URL and drops the rest", () => {
  const f = fromParams(new URLSearchParams("category=ml&category=bogus&category=quant"));
  expect(f.category).toEqual(["ml", "quant"]);
  expect(toParams(f).getAll("category")).toEqual(["ml", "quant"]);
  expect(activeCount(f)).toBe(2);
});
