import { pairKey, pathGhosts, pathSimLinks, seedGhosts } from "./pathDraw";
import type { SimLink } from "./types";

const path = [["gk", "od"], ["od", "nc"]] as const;

describe("a shortest path on the canvas (flag graph-algos)", () => {
  it("the ghosts are the path's pages the view does not draw, in path order", () => {
    expect(pathGhosts(path, new Set(["gk", "nc"]))).toEqual(["od"]);
    expect(pathGhosts(path, new Set(["gk", "od", "nc"]))).toEqual([]);
    expect(pathGhosts(path, new Set())).toEqual(["gk", "od", "nc"]);
  });

  it("a ghost is pinned at the middle of its placed neighbours", () => {
    const prev = new Map<string, { x?: number; y?: number; fx?: number; fy?: number }>([
      ["gk", { x: 0, y: 0 }],
      ["nc", { x: 100, y: 50 }],
    ]);
    expect(seedGhosts(prev, ["od"], path)).toEqual(["od"]);
    expect(prev.get("od")).toEqual({ x: 50, y: 25, fx: 50, fy: 25 });
  });

  it("a run of ghosts is placed in turn; a ghost with a place already keeps it", () => {
    const run = [["a", "g1"], ["g1", "g2"], ["g2", "b"]] as const;
    const prev = new Map<string, { x?: number; y?: number; fx?: number; fy?: number }>([
      ["a", { x: 0, y: 0 }],
      ["b", { x: 90, y: 0 }],
    ]);
    expect(seedGhosts(prev, ["g1", "g2"], run).sort()).toEqual(["g1", "g2"]);
    expect(prev.get("g1")?.x).toBeTypeOf("number");
    const kept = new Map([["od", { x: 7, y: 7, fx: 7, fy: 7 }]]);
    expect(seedGhosts(kept, ["od"], path)).toEqual([]);
  });

  it("the path's links in the drawn data, in order, either direction", () => {
    const l = (source: string, target: string) => ({ source, target, kind: "wikilink" }) as SimLink;
    const links = [l("x", "y"), l("nc", "od"), l("gk", "od")];
    expect(pathSimLinks(links, path)).toEqual([links[2], links[1]]);
    expect(pathSimLinks([l("x", "y")], path)).toEqual([]);
    expect(pairKey("b", "a")).toBe(pairKey("a", "b"));
  });
});

describe("a path the view hides whole", () => {
  it("its ghosts go in a row from the origin, pinned", () => {
    const prev = new Map<string, { x?: number; y?: number; fx?: number; fy?: number }>();
    expect(seedGhosts(prev, ["gk", "od", "nc"], path, { x: 10, y: 5 })).toEqual(["gk", "od", "nc"]);
    expect([...prev.values()].map((p) => p.x)).toEqual([-50, 10, 70]);
    expect([...prev.values()].every((p) => p.fy === 5)).toBe(true);
  });
});
