import { describe, expect, it } from "vitest";
import { buildNeighborMap } from "./graphData";
import { node, sampleLinks, sampleNodes } from "./fixtures";
import { boxContains, citationNeighbours, memberSources, neighboursOf, onlyType, pickInRegion, polyContains, routeOf, typesOf, visibleAdjacency, type Pt } from "./selection";
import type { GNode } from "./types";

const byId = new Map<string, GNode>(sampleNodes.map((n) => [n.id, n]));

describe("regions", () => {
  it("a box contains points whichever corner it was dragged from", () => {
    expect(boxContains({ x: 10, y: 10 }, { x: 0, y: 0 }, { x: 5, y: 5 })).toBe(true);
    expect(boxContains({ x: 0, y: 10 }, { x: 10, y: 0 }, { x: 11, y: 5 })).toBe(false);
  });

  it("a lasso is even-odd", () => {
    const tri: Pt[] = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 0, y: 10 }];
    expect(polyContains(tri, { x: 2, y: 2 })).toBe(true);
    expect(polyContains(tri, { x: 8, y: 8 })).toBe(false);
  });

  it("picks the ids inside, skipping nodes that have no position yet", () => {
    const at: Record<string, Pt | null> = { a: { x: 1, y: 1 }, b: { x: 50, y: 50 }, c: null };
    expect(pickInRegion({ kind: "box", a: { x: 0, y: 0 }, b: { x: 10, y: 10 } }, ["a", "b", "c"], (id) => at[id] ?? null)).toEqual(["a"]);
  });
});

describe("expansion", () => {
  const visible = new Set(["idea-margin", "topic-learning-theory", "2019-fine-grained"]);

  it("neighbours follow only links between drawn pages and never repeat the selection", () => {
    const adj = visibleAdjacency(sampleLinks, visible);
    expect(neighboursOf(["idea-margin"], adj).sort()).toEqual(["2019-fine-grained", "topic-learning-theory"]);
    expect(neighboursOf(["idea-margin", "topic-learning-theory"], adj)).toEqual(["2019-fine-grained"]);
  });

  it("members expand a non-source page to its source neighbours over every link", () => {
    const all = buildNeighborMap(sampleLinks);
    expect(memberSources(["idea-margin"], all, byId).sort()).toEqual(["2019-fine-grained", "2020-listed-paper"]);
    expect(memberSources(["2019-fine-grained"], all, byId)).toEqual([]);
  });

  it("citation neighbours go both ways and only to known pages", () => {
    const links = [{ source: "a", target: "b" }, { source: "c", target: "a" }, { source: "a", target: "zzz" }];
    expect(citationNeighbours(new Set(["a"]), links, new Set(["a", "b", "c"])).sort()).toEqual(["b", "c"]);
  });
});

describe("selection helpers", () => {
  it("lists the types and keeps one of them", () => {
    const ids = ["idea-margin", "topic-learning-theory", "2019-fine-grained"];
    expect(typesOf(ids, byId)).toEqual(["idea", "paper", "topic"]);
    expect(onlyType(ids, byId, "paper")).toEqual(["2019-fine-grained"]);
  });

  it("takes the first route of a path answer, or nothing", () => {
    expect(routeOf({ a: "x", b: "y", paths: [{ nodes: ["x", "m", "y"], hops: [] }] })).toEqual(["x", "m", "y"]);
    expect(routeOf({ a: "x", b: "y", paths: [] })).toEqual([]);
    expect(node("n").id).toBe("n");
  });
});
