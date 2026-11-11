import { describe, expect, it } from "vitest";
import { CITE_STATUS, citationMap, MISSING_STEP, missingGrid, statusRamp } from "./citationMapData";

const g = {
  nodes: [
    { id: "a", title: "A", year: 2001, citationCount: 10 },
    { id: "b", title: "B", year: null, citationCount: 0 },
    { id: "c", title: "C", citationCount: 3 },
    { id: "lonely", title: "Lonely", year: 2020, citationCount: 1 },
    { id: "outside", title: "Not cataloged", citationCount: 99 },
  ],
  links: [
    { source: "a", target: "b" },
    { source: "a", target: "b" },
    { source: "c", target: "a" },
    { source: "c", target: "c" },
    { source: "a", target: "outside" },
  ],
};
const cataloged = new Set(["a", "b", "c", "lonely"]);
const papers = [
  { id: "a", title: "A", depth: "deep" },
  { id: "b", title: "B", depth: "easy" },
  { id: "c", title: "C", depth: "listed" },
  { id: "lonely", title: "Lonely", depth: "full" },
  { id: "missed", title: "Missed", depth: "full" },
];

describe("the citation map", () => {
  const m = citationMap(g, (id) => cataloged.has(id), papers);

  it("keeps cataloged papers and the cites links among them, once each, no self links", () => {
    expect(m.links).toEqual([
      { source: "a", target: "b" },
      { source: "c", target: "a" },
    ]);
    expect(m.papers).toBe(4);
    expect(m.linked).toBe(3);
    expect(m.nodes.find((n) => n.id === "outside")).toBeUndefined();
    expect(m.nodes.find((n) => n.id === "lonely")?.isolated).toBe(true);
    expect(m.nodes.find((n) => n.id === "a")?.isolated).toBe(false);
  });

  it("colours by status: the digest depth for papers with data, failed for a vault paper without any", () => {
    const st = Object.fromEntries(m.nodes.map((n) => [n.id, n.status]));
    expect(st).toEqual({ a: "deep", b: "easy", c: "listed", lonely: "full", missed: "failed" });
    expect(m.withoutData).toBe(1);
    expect(m.nodes.find((n) => n.id === "missed")).toMatchObject({ isolated: true, citationCount: 0 });
  });

  it("a paper with data but no known depth counts as listed", () => {
    expect(citationMap(g, (id) => cataloged.has(id)).nodes.every((n) => n.status === "listed")).toBe(true);
  });

  it("the legend spells out each step of one ordered ramp, red to strongest green", () => {
    expect(CITE_STATUS.map((s) => s.key)).toEqual(["failed", "listed", "easy", "full", "deep"]);
    const r = statusRamp("#00ff00", "#ff0000");
    expect(r.failed).toBe("#ff0000");
    const alpha = (c: string) => Number(/,\s*([\d.]+)\)$/.exec(c)?.[1]);
    expect([r.listed, r.easy, r.full, r.deep].map(alpha)).toEqual([0.3, 0.5, 0.75, 1]);
  });
});

describe("the grid of papers without data", () => {
  it("sits right of the core, centred on its middle, one spot per paper, none shared", () => {
    const g = missingGrid(10, 100, 40);
    expect(g).toHaveLength(10);
    expect(Math.min(...g.map((p) => p.x))).toBeGreaterThan(100);
    const ys = g.map((p) => p.y);
    expect((Math.min(...ys) + Math.max(...ys)) / 2).toBeCloseTo(40);
    expect(new Set(g.map((p) => `${p.x},${p.y}`)).size).toBe(10);
    expect(g[1]!.x - g[0]!.x).toBe(MISSING_STEP);
  });
});
