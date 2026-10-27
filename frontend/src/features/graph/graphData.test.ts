import { sampleLinks, sampleNodes } from "./fixtures";
import { buildGraphData, buildNeighborMap, edgeWeight, edgeWeights, largestComponent, sameSet, sharedSourceLinks, sourcesDrawn, sourcesOf, withNeighbors } from "./graphData";
import type { GraphModel } from "./types";

const model: GraphModel = {
  nodes: sampleNodes,
  links: sampleLinks,
  conceptLinks: [{ source: "idea-margin", target: "topic-learning-theory", shared: 2 }, { source: "idea-margin", target: "q-why-big-nets-work", shared: 3 }],
};
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));

describe("buildNeighborMap", () => {
  it("is undirected and de-duplicated", () => {
    const m = buildNeighborMap([{ source: "a", target: "b" }, { source: "b", target: "a" }, { source: "a", target: "c" }]);
    expect(m.get("a")).toEqual(["b", "c"]);
    expect(m.get("b")).toEqual(["a"]);
  });
});

describe("sourcesOf / sourcesDrawn", () => {
  const nb = buildNeighborMap(sampleLinks);
  it("lists the source-layer neighbours of a concept or collection", () => {
    expect(sourcesOf("idea-margin", nb, byId).sort()).toEqual(["2019-fine-grained", "2020-listed-paper"]);
    expect(sourcesOf("course-runi-rl", nb, byId)).toEqual(["2019-fine-grained"]);
  });
  it("tells whether any source page is drawn", () => {
    expect(sourcesDrawn(new Set(["idea-margin"]), byId)).toBe(false);
    expect(sourcesDrawn(new Set(["idea-margin", "2019-fine-grained"]), byId)).toBe(true);
  });
});

describe("buildGraphData", () => {
  it("keeps visible nodes and the links between them", () => {
    const d = buildGraphData(model, new Set(["idea-margin", "topic-learning-theory", "2019-fine-grained"]));
    expect(d.nodes.map((n) => n.id).sort()).toEqual(["2019-fine-grained", "idea-margin", "topic-learning-theory"]);
    expect(d.links.filter((l) => l.kind !== "shared")).toHaveLength(3);
  });
  it("adds thin shared-source edges while no source is drawn, only for unlinked concept pairs", () => {
    const d = buildGraphData(model, new Set(["idea-margin", "topic-learning-theory", "q-why-big-nets-work"]), undefined, true);
    const shared = d.links.filter((l) => l.kind === "shared");
    // idea-margin <-> topic is already linked by a wikilink; idea-margin <-> question is not
    expect(shared).toEqual([{ source: "idea-margin", target: "q-why-big-nets-work", kind: "shared", shared: 3 }]);
  });
  it("hides shared edges by default (SHOW_SHARED_EDGES)", () => {
    const d = buildGraphData(model, new Set(["idea-margin", "topic-learning-theory", "q-why-big-nets-work"]));
    expect(d.links.some((l) => l.kind === "shared")).toBe(false);
  });
  it("draws no shared edges once a source page is on screen", () => {
    const d = buildGraphData(model, new Set(["idea-margin", "q-why-big-nets-work", "2019-fine-grained"]));
    expect(d.links.some((l) => l.kind === "shared")).toBe(false);
  });
  it("carries positions over for nodes that stay", () => {
    const d = buildGraphData(model, new Set(["idea-margin", "topic-learning-theory"]), new Map([["idea-margin", { x: 3, y: 4, fx: 3 }], ["gone", { x: 1, y: 1 }]]));
    const n = d.nodes.find((m) => m.id === "idea-margin");
    expect([n?.x, n?.y, n?.fx]).toEqual([3, 4, 3]);
    expect(d.nodes.find((m) => m.id === "topic-learning-theory")?.x).toBeUndefined();
  });
  it("does not share link objects with the model (force-graph mutates them)", () => {
    const d = buildGraphData(model, new Set(sampleNodes.map((n) => n.id)));
    expect(d.links[0]).not.toBe(sampleLinks[0]);
  });
});

describe("edgeWeights", () => {
  it("counts links in both directions and adds the shared-source count", () => {
    const w = edgeWeights({
      links: [
        { source: "a", target: "b", kind: "wikilink" },
        { source: "b", target: "a", kind: "related" },
        { source: "a", target: "c", kind: "book" },
        { source: "a", target: "d", kind: "shared", shared: 9 },
      ],
      conceptLinks: [{ source: "b", target: "a", shared: 3 }],
    });
    expect(edgeWeight(w, "a", "b")).toBe(5);
    expect(edgeWeight(w, "b", "a")).toBe(5);
    expect(edgeWeight(w, "c", "a")).toBe(1);
    expect(edgeWeight(w, "a", "d")).toBe(0); // shared edges are derived, not links
    expect(edgeWeight(w, "a", "z")).toBe(0);
  });
});

describe("sharedSourceLinks", () => {
  it("skips pairs with an end that is not drawn", () => {
    expect(sharedSourceLinks(model.conceptLinks, new Set(["idea-margin"]), new Set())).toEqual([]);
  });
});

describe("withNeighbors / largestComponent", () => {
  const nb = buildNeighborMap([{ source: "a", target: "b" }, { source: "b", target: "c" }, { source: "x", target: "y" }]);
  it("expands a set by one step", () => {
    expect([...withNeighbors(["a"], nb)].sort()).toEqual(["a", "b"]);
  });
  it("finds the biggest connected part of what is drawn", () => {
    expect([...largestComponent(new Set(["a", "b", "c", "x", "y", "z"]), nb)].sort()).toEqual(["a", "b", "c"]);
    expect([...largestComponent(new Set(["a", "c", "x", "y"]), nb)].sort()).toEqual(["x", "y"]);
  });
  it("copes with an empty set", () => {
    expect(largestComponent(new Set(), nb).size).toBe(0);
  });
});

describe("sameSet", () => {
  it("compares members, not Set identity", () => {
    expect(sameSet(new Set(["a", "b"]), new Set(["b", "a"]))).toBe(true);
    expect(sameSet(new Set(["a"]), new Set(["a", "b"]))).toBe(false);
    expect(sameSet(new Set(["a", "c"]), new Set(["a", "b"]))).toBe(false);
  });
});
