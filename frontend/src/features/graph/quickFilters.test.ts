import { buildNeighborMap } from "./graphData";
import { node } from "./fixtures";
import { applyQuick, kCore, QUICK_OFF, shortestPaths } from "./quickFilters";

// a triangle a-b-c with a tail c-d-e, and an orphan f
const links = [
  ["a", "b"],
  ["b", "c"],
  ["c", "a"],
  ["c", "d"],
  ["d", "e"],
].map(([source, target]) => ({ source: source!, target: target! }));
const nb = buildNeighborMap(links);
const ids = ["a", "b", "c", "d", "e", "f"];
const all = new Set(ids);
const byId = new Map(ids.map((id) => [id, node(id, { added: id === "f" ? "2026-10-20" : "2026-01-01" })]));
const now = Date.parse("2026-10-25");
const sorted = (s: Set<string>) => [...s].sort();

describe("quick filters", () => {
  it("off keeps everything", () => {
    expect(sorted(applyQuick(all, byId, nb, new Set(), QUICK_OFF, now))).toEqual(ids);
  });
  it("Connected drops pages with too few links among those shown", () => {
    expect(sorted(applyQuick(all, byId, nb, new Set(), { ...QUICK_OFF, connected: 2 }, now))).toEqual(["a", "b", "c", "d"]);
  });
  it("Backbone peels the tail: the 2-core is the triangle", () => {
    expect(sorted(kCore(all, nb, 2))).toEqual(["a", "b", "c"]);
  });
  it("Neighbours keeps the selection's hops and hides the rest", () => {
    expect(sorted(applyQuick(all, byId, nb, new Set(["e"]), { ...QUICK_OFF, neighbours: 2 }, now))).toEqual(["c", "d", "e"]);
  });
  it("Path keeps every page on a shortest path between the two selected", () => {
    expect(sorted(shortestPaths(all, nb, "a", "e"))).toEqual(["a", "c", "d", "e"]);
    expect(sorted(applyQuick(all, byId, nb, new Set(["a", "e"]), { ...QUICK_OFF, path: true }, now))).toEqual(["a", "c", "d", "e"]);
  });
  it("Recent keeps pages added in the window, and the selection always stays", () => {
    expect(sorted(applyQuick(all, byId, nb, new Set(), { ...QUICK_OFF, recent: 7 }, now))).toEqual(["f"]);
    expect(sorted(applyQuick(all, byId, nb, new Set(["a"]), { ...QUICK_OFF, recent: 7 }, now))).toEqual(["a", "f"]);
  });
});
