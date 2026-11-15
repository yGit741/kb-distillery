import { calmEdge, edgeWidth, zoomIn } from "./edgeWeight";

describe("a link's weight follows the zoom", () => {
  it("is at rest at the whole-graph fit and full once a handful of pages fill the screen", () => {
    expect(zoomIn(0.6)).toBe(0);
    expect(zoomIn(0.72)).toBe(0);
    expect(zoomIn(5.6)).toBe(1);
    expect(zoomIn(40)).toBe(1);
  });

  it("grows steadily in between, and never fails on a zoom that is not a number yet", () => {
    const steps = [0.8, 1, 1.5, 2, 3, 4, 5].map(zoomIn);
    for (let i = 1; i < steps.length; i++) expect(steps[i]!).toBeGreaterThan(steps[i - 1]!);
    expect(zoomIn(0)).toBe(zoomIn(1));
    expect(zoomIn(Number.NaN)).toBe(zoomIn(1));
  });

  it("draws a link close to 1 px at the fit and as a line up close", () => {
    expect(edgeWidth("links", undefined, 0.7)).toBeCloseTo(0.95);
    expect(edgeWidth("links", undefined, 6)).toBeCloseTo(0.95 * 1.75);
    expect(edgeWidth("cites", undefined, 6)).toBeGreaterThan(1.5);
  });

  it("a shared-sources link is wider the more it shares, up to six", () => {
    const at = (shared?: number) => edgeWidth("shared", shared, 0.7);
    expect(at(1)).toBeCloseTo(0.68);
    expect(at(undefined)).toBe(at(1));
    expect(at(3)).toBeGreaterThan(at(1));
    expect(at(6)).toBeCloseTo(1.33);
    expect(at(40)).toBe(at(6));
    // one shared source is still lighter than a direct link, at every zoom
    for (const k of [0.7, 2, 6]) expect(edgeWidth("shared", 1, k)).toBeLessThan(edgeWidth("links", undefined, k));
  });

  it("calm edges rest quiet at the fit and stay below full strength up close", () => {
    expect(calmEdge(0.7)).toBeCloseTo(0.55);
    expect(calmEdge(6)).toBeCloseTo(0.85);
    expect(calmEdge(2)).toBeGreaterThan(calmEdge(0.7));
    expect(calmEdge(100)).toBeLessThan(1);
  });
});
