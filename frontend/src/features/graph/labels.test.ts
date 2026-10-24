import { node } from "./fixtures";
import { buildNeighborMap } from "./graphData";
import { declutter, hubCount, HUB_BUDGET, labelRanks, labelText, RANK, shortSlug, type LabelInput, type Placed } from "./labels";
import type { GNode } from "./types";

function make(n: number): GNode[] {
  const out: GNode[] = [];
  for (let i = 0; i < n; i++) out.push(node(`topic-${String(i).padStart(2, "0")}`, { type: "topic", inDegree: 50 - i }));
  for (let i = 0; i < n; i++) out.push(node(`paper-${String(i).padStart(2, "0")}`, { type: "paper", layer: "source", inDegree: 100 - i }));
  out.push(node("course-x", { type: "course", layer: "collection", inDegree: 1 }));
  return out;
}

function input(nodes: GNode[], o: Partial<LabelInput> = {}): LabelInput {
  return {
    visible: new Set(nodes.map((n) => n.id)),
    byId: new Map(nodes.map((n) => [n.id, n] as const)),
    neighbors: buildNeighborMap([]),
    hovered: null,
    selected: new Set(),
    mode: "auto",
    typeLabels: new Set(),
    zoomRatio: 1,
    ...o,
  };
}

describe("hub labels", () => {
  const nodes = make(30);
  it("labels about a dozen collections and topics at fit zoom, never a paper", () => {
    const r = labelRanks(input(nodes));
    expect(r.size).toBe(HUB_BUDGET);
    expect([...r.keys()].every((id) => !id.startsWith("paper-"))).toBe(true);
    expect(r.has("topic-00")).toBe(true); // most linked first
    expect(r.has("topic-29")).toBe(false);
  });
  it("shows more as you zoom in, and then any page by link count", () => {
    expect(hubCount(1)).toBe(12);
    expect(hubCount(0.3)).toBe(12);
    expect(hubCount(4)).toBe(96);
    const near = labelRanks(input(nodes, { zoomRatio: 2 }));
    expect(near.size).toBe(hubCount(2));
    expect([...near.keys()].some((id) => id.startsWith("paper-"))).toBe(true);
  });
  it("falls back to the most linked pages when no hub is drawn", () => {
    const papers = nodes.filter((n) => n.type === "paper");
    expect(labelRanks(input(papers)).size).toBe(HUB_BUDGET);
  });
});

describe("hover and selection", () => {
  const nodes = make(5);
  const nb = buildNeighborMap([{ source: "topic-00", target: "paper-00" }, { source: "topic-00", target: "paper-01" }]);
  it("hover always labels the node (even with labels off) and ranks first", () => {
    const r = labelRanks(input(nodes, { mode: "off", hovered: "paper-04", neighbors: nb }));
    expect([...r.entries()]).toEqual([["paper-04", RANK.hover]]);
  });
  it("a click labels the node and its neighbours", () => {
    const r = labelRanks(input(nodes, { mode: "off", selected: new Set(["topic-00"]), neighbors: nb }));
    expect(r.get("topic-00")).toBe(RANK.selected);
    expect(r.get("paper-00")).toBe(RANK.near);
    expect(r.get("paper-01")).toBe(RANK.near);
    expect(r.size).toBe(3);
  });
  it("hover mode labels the hovered neighbourhood", () => {
    const r = labelRanks(input(nodes, { mode: "hover", hovered: "topic-00", neighbors: nb }));
    expect(r.size).toBe(3);
  });
  it("keeps the best rank when a page is both hovered and selected, and skips hidden pages", () => {
    const vis = new Set(["topic-00"]);
    const r = labelRanks(input(nodes, { visible: vis, hovered: "topic-00", selected: new Set(["topic-00", "paper-00"]), neighbors: nb, mode: "off" }));
    expect([...r.entries()]).toEqual([["topic-00", RANK.hover]]);
  });
  it("type labels and 'all' add every matching page", () => {
    const t = labelRanks(input(nodes, { mode: "off", typeLabels: new Set(["paper"]) }));
    expect(t.size).toBe(5);
    expect(labelRanks(input(nodes, { mode: "all" })).size).toBe(nodes.length);
  });
});

describe("declutter", () => {
  const p = (id: string, rank: number, x: number, deg = 1): Placed => ({ id, rank, deg, box: { x1: x, y1: 0, x2: x + 10, y2: 4 } });
  it("drops a label that overlaps a more important one", () => {
    const kept = declutter([p("low", 4, 5), p("high", 4, 0, 9), p("far", 4, 30)], 12).map((k) => k.id);
    expect(kept).toEqual(["high", "far"]);
  });
  it("never drops the hovered label", () => {
    const kept = declutter([p("a", 4, 0, 9), p("hover", 0, 2)], 12).map((k) => k.id);
    expect(kept).toEqual(["hover"]); // the overlapping, less important label gives way
  });
  it("lets a boundary touch pass", () => {
    expect(declutter([p("a", 4, 0), p("b", 4, 10)], 12)).toHaveLength(2);
  });
});

describe("label text", () => {
  it("truncates long titles unless full", () => {
    const n = node("x", { title: "a".repeat(60) });
    expect(labelText(n, "title")).toHaveLength(41);
    expect(labelText(n, "title", true)).toHaveLength(60);
    expect(labelText(n, "slug")).toBe("x");
    expect(labelText(node("only-slug", { title: "" }), "title")).toBe("only-slug");
  });
  it("shortens long slugs", () => {
    expect(shortSlug("a-b-c-d-e")).toBe("a-b-c…");
    expect(shortSlug("a-b")).toBe("a-b");
  });
});
