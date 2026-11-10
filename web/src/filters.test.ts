import { describe, expect, it } from "vitest";
import { DEFAULTS, type Filters, fromParams, toParams } from "./filters";

const sets: Filters[] = [
  DEFAULTS,
  { ...DEFAULTS, view: "all", company: ["google", "nvidia"], loc: "india", q: "ml" },
  { ...DEFAULTS, elig: ["ok", "warn"], posted: "7d", tag: ["liked", "untagged"], dismissed: true },
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
});
