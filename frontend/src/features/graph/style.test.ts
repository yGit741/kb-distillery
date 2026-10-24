import { node } from "./fixtures";
import { colorKey, colorOf, nodeRadius } from "./style";
import { TYPE_COLORS, DEPTH_COLORS, LAYER_COLORS, UNKNOWN_COLOR } from "@/theme/palette";

describe("colorOf", () => {
  const paper = node("p", { type: "paper", layer: "source", depth: "deep", status: "digested", areas: ["info-theory"], inDegree: 7, outDegree: 6 });
  it("takes colours from the one data palette", () => {
    expect(colorOf(paper, "type")).toBe(TYPE_COLORS.paper);
    expect(colorOf(paper, "layer")).toBe(LAYER_COLORS.source);
    expect(colorOf(paper, "depth")).toBe(DEPTH_COLORS.deep);
    expect(colorOf(node("c"), "depth")).toBe(UNKNOWN_COLOR);
  });
  it("bands the link count", () => {
    expect(colorOf(paper, "degree")).toBe("#ff6b7a");
    expect(colorKey(paper, "degree")).toBe("12+ links");
    expect(colorKey(node("z"), "degree")).toBe("0–1 links");
  });
  it("names the key per colouring", () => {
    expect(colorKey(paper, "depth")).toBe("deep");
    expect(colorKey(node("c"), "depth")).toBe("(not a source)");
    expect(colorKey(paper, "area")).toBe("info-theory");
    expect(colorKey(node("c"), "status")).toBe("growing");
    expect(colorKey(node("c"), "none")).toBe("All pages");
  });
});

describe("nodeRadius", () => {
  const base = { by: "connections" as const, base: 5 };
  it("grows with links through a square root and caps at 24", () => {
    const r0 = nodeRadius(node("a"), base);
    const r3 = nodeRadius(node("a", { inDegree: 3 }), base);
    const r24 = nodeRadius(node("a", { inDegree: 24 }), base);
    const r99 = nodeRadius(node("a", { inDegree: 99 }), base);
    expect(r0).toBeCloseTo(3);
    expect(r3).toBeGreaterThan(r0);
    expect(r24).toBeCloseTo(8);
    expect(r99).toBe(r24);
    expect((r3 - r0) / 3).toBeGreaterThan((r24 - r3) / 21); // concave: the first links count most
  });
  it("draws a collection as a larger hub", () => {
    const m = node("c", { layer: "collection", type: "course", inDegree: 2 });
    expect(nodeRadius(m, base)).toBeCloseTo(nodeRadius(node("c", { inDegree: 2 }), base) * 1.5);
  });
  it("uniform ignores links; in/out pick one direction", () => {
    const n = node("a", { inDegree: 10, outDegree: 0 });
    expect(nodeRadius(n, { by: "uniform", base: 4 })).toBe(4);
    expect(nodeRadius(n, { by: "out", base: 5 })).toBeCloseTo(3);
    expect(nodeRadius(n, { by: "in", base: 5 })).toBeGreaterThan(3);
  });
});

describe("lab size and colour modes", () => {
  it("tier sizes topics above ideas above sources", () => {
    const o = { by: "tier" as const, base: 4, range: 2 };
    expect(nodeRadius(node("t", { type: "topic" }), o)).toBeGreaterThan(nodeRadius(node("i", { type: "idea" }), o));
    expect(nodeRadius(node("p", { type: "paper", layer: "source" }), o)).toBe(4);
  });
  it("metric modes read the importance signal, with perceptual scaling", () => {
    const o = { by: "evidence" as const, base: 4, range: 2, metric: () => 0.25 };
    expect(nodeRadius(node("a"), o)).toBeCloseTo(4 * (1 + 2 * 0.25));
    expect(nodeRadius(node("a"), { ...o, perceptual: true })).toBeCloseTo(4 * (1 + 2 * Math.pow(0.25, 0.57)));
  });
  it("evidence colour is grey without a signal and sequential with one", () => {
    expect(colorOf(node("a"), "evidence")).toBe(UNKNOWN_COLOR);
    expect(colorOf(node("a"), "evidence", 1)).toBe("rgb(31, 91, 214)");
  });
});
