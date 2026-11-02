import { node } from "../fixtures";
import { buildNeighborMap } from "../graphData";
import type { GNode } from "../types";
import { DEFAULT_LAB } from "./config";
import { betweenness, computeImportance, hopsFrom, pagerank, visibleAdjacency } from "./importance";

const nodes: GNode[] = [
  node("theme-a", { type: "topic", areas: ["a"] }),
  node("idea-1", { type: "idea", areas: ["a"] }),
  node("idea-2", { type: "idea", areas: ["a"] }),
  node("q-1", { type: "question", maturity: "open" }),
  node("paper-deep", { type: "paper", layer: "source", depth: "deep" }),
  node("paper-easy", { type: "paper", layer: "source", depth: "easy" }),
  node("hub", { type: "series", layer: "collection", inDegree: 1400 }),
];
const links = [
  { source: "theme-a", target: "idea-1" },
  { source: "theme-a", target: "idea-2" },
  { source: "idea-1", target: "paper-deep" },
  { source: "idea-1", target: "paper-easy" },
  { source: "idea-2", target: "paper-easy" },
  { source: "q-1", target: "idea-1" },
  { source: "hub", target: "paper-easy" },
];
const byId = new Map(nodes.map((n) => [n.id, n] as const));
const neighbors = buildNeighborMap(links);
const all = new Set(nodes.map((n) => n.id));

describe("computeImportance", () => {
  it("ranks by type tier and digested evidence, not by link count", () => {
    const imp = computeImportance({ visible: all, byId, neighbors, cfg: DEFAULT_LAB });
    const s = (id: string) => imp.score.get(id) as number;
    expect(s("theme-a")).toBeGreaterThan(s("hub")); // 1400 links do not make the import hub important
    expect(s("idea-1")).toBeGreaterThan(s("idea-2")); // more and deeper sources
    expect(imp.terms.get("q-1")?.open).toBe(1);
    expect(imp.qrank.get("idea-1")).toBe(0); // deep evidence outranks a topic with none of its own
  });
  it("evidence weighs a deep read above an easy skim, and the easy weight is a knob", () => {
    const imp = computeImportance({ visible: all, byId, neighbors, cfg: { ...DEFAULT_LAB, norm: "global" } });
    expect(imp.terms.get("paper-deep")?.evidence).toBeGreaterThan(imp.terms.get("paper-easy")?.evidence as number);
    const none = computeImportance({ visible: all, byId, neighbors, cfg: { ...DEFAULT_LAB, norm: "global", easyWeight: 0 } });
    expect(none.terms.get("idea-2")?.evidence).toBe(0);
  });
  it("only counts what is drawn", () => {
    const vis = new Set(["theme-a", "idea-1"]);
    const imp = computeImportance({ visible: vis, byId, neighbors, cfg: DEFAULT_LAB });
    expect([...imp.score.keys()].sort()).toEqual(["idea-1", "theme-a"]);
    expect(imp.terms.get("idea-1")?.orphan).toBe(1);
  });
  it("a zero weight drops a signal from the score", () => {
    const cfg = { ...DEFAULT_LAB, wTier: 0, wEvidence: 0, wOpen: 0, wOrphan: 1 };
    const imp = computeImportance({ visible: all, byId, neighbors, cfg });
    expect(imp.score.get("theme-a")).toBe(0); // two links: not an orphan
  });
});

describe("graph measures", () => {
  const adj = visibleAdjacency(all, neighbors);
  it("betweenness peaks on the bridge", () => {
    const b = betweenness(adj);
    const top = [...b.entries()].sort((x, y) => y[1] - x[1])[0]?.[0];
    expect(top).toBe("idea-1");
  });
  it("pagerank sums to one", () => {
    const pr = pagerank(adj);
    expect([...pr.values()].reduce((a, v) => a + v, 0)).toBeCloseTo(1, 5);
  });
  it("hops from the selection stop at the limit", () => {
    const h = hopsFrom(["theme-a"], all, neighbors, 1);
    expect(h.get("theme-a")).toBe(0);
    expect(h.get("idea-1")).toBe(1);
    expect(h.has("paper-deep")).toBe(false);
  });
});
