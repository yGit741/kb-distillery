import { DIMENSIONS, dimensionsFor } from "./colourDimensions";
import { BAR_BY, colorOf, freshness, ordinalOf, RAMP_BY, RAMP_MEANING } from "./style";
import { sampleNodes } from "./fixtures";

describe("the legend's Color by dimensions", () => {
  it("concepts and sources each offer their own list", () => {
    expect(DIMENSIONS.concepts.map((d) => d.label)).toEqual(["theme", "type", "maturity", "recency", "source count"]);
    expect(DIMENSIONS.sources.map((d) => d.label)).toEqual(["format", "digest status", "date added"]);
  });

  it("both subjects together list a shared colouring once, under its first name", () => {
    expect(dimensionsFor(["concepts", "sources"]).map((d) => d.label)).toEqual(["theme", "type", "maturity", "recency", "source count", "digest status", "date added"]);
    expect(dimensionsFor(["sources"]).map((d) => d.by)).toEqual(["format", "depth", "added"]);
  });

  it("every continuous dimension is on the ramp and names its two ends", () => {
    for (const by of BAR_BY) {
      expect(RAMP_BY.has(by)).toBe(true);
      expect(RAMP_MEANING[by]).toBeDefined();
    }
  });
});

describe("recency and date added", () => {
  const now = Date.parse("2026-11-14T00:00:00Z");
  it("freshness steps from this week down to a year or more", () => {
    expect(freshness("2026-11-12", now)).toBe(1);
    expect(freshness("2026-10-20", now)).toBe(0.75);
    expect(freshness("2026-09-01", now)).toBe(0.5);
    expect(freshness("2026-01-01", now)).toBe(0.25);
    expect(freshness("2024-01-01", now)).toBe(0);
    expect(freshness("", now)).toBeUndefined();
    expect(freshness("not a date", now)).toBeUndefined();
  });

  it("recency reads the last change, date added the day the page arrived; a page without a date is grey, not a step", () => {
    const n = { ...sampleNodes[0]!, added: "2020-01-01", changed: new Date().toISOString() };
    expect(ordinalOf(n, "recency")).toBe(1);
    expect(ordinalOf(n, "added")).toBe(0);
    const bare = { ...n, added: "", changed: "" };
    expect(ordinalOf(bare, "recency")).toBeUndefined();
    expect(colorOf(bare, "recency", undefined, "light")).toBe(colorOf(bare, "added", undefined, "light"));
    expect(colorOf(n, "recency", undefined, "light")).not.toBe(colorOf(bare, "recency", undefined, "light"));
  });

  it("format colours a page by its type", () => {
    const [a] = sampleNodes;
    expect(colorOf(a!, "format")).toBe(colorOf(a!, "type"));
  });
});

describe("the freshness steps are the legend bar's steps", () => {
  it("every value freshness returns is one of the ramp's RAMP_STEPS stops", async () => {
    const { RAMP_STEPS, rampStep } = await import("./style");
    const now = Date.parse("2026-11-14T00:00:00Z");
    for (const d of ["2026-11-12", "2026-10-20", "2026-09-01", "2026-01-01", "2024-01-01"]) {
      const t = freshness(d, now)!;
      expect(rampStep(t)).toBe(t);
      expect(Number.isInteger(t * (RAMP_STEPS - 1))).toBe(true);
    }
  });
});
