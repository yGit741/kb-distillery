import { centrality, cliques, communities, cutsAndBridges, kCore, top, within } from "./algos";

const graph = (edges: string): Map<string, Set<string>> => {
  const adj = new Map<string, Set<string>>();
  for (const e of edges.split(/\s+/).filter(Boolean)) {
    const [a, b] = e.split("-") as [string, string];
    (adj.get(a) ?? adj.set(a, new Set()).get(a)!).add(b);
    (adj.get(b) ?? adj.set(b, new Set()).get(b)!).add(a);
  }
  return adj;
};
const sorted = (s: Iterable<string>) => [...s].sort();

// two triangles joined by one link (the bridge c-d), and a tail d-g
const dumbbell = graph("a-b b-c c-a d-e e-f f-d c-d d-g");

describe("graph algorithms", () => {
  it("cliques: maximal ones of at least the size asked", () => {
    const r = cliques(dumbbell, 3);
    expect(sorted(r.pages)).toEqual(["a", "b", "c", "d", "e", "f"]);
    expect(r.count).toBe(2);
    expect(r.capped).toBe(false);
    const k4 = graph("a-b a-c a-d b-c b-d c-d d-e");
    expect(sorted(cliques(k4, 4).pages)).toEqual(["a", "b", "c", "d"]);
    expect(cliques(k4, 5).pages.size).toBe(0);
  });

  it("k-core: the tail drops out of the 2-core, nothing is left of the 3-core", () => {
    expect(sorted(kCore(dumbbell, 2))).toEqual(["a", "b", "c", "d", "e", "f"]);
    expect(kCore(dumbbell, 3).size).toBe(0);
  });

  it("cut vertices and bridges", () => {
    const r = cutsAndBridges(dumbbell);
    expect(sorted(r.cuts)).toEqual(["c", "d"]);
    expect(r.bridges.map((b) => b.slice().sort().join("-")).sort()).toEqual(["c-d", "d-g"]);
    expect(sorted(r.bridgeEnds)).toEqual(["c", "d", "g"]);
  });

  it("centrality: the bridge pages carry the paths; a star's centre wins every measure", () => {
    expect(sorted(top(centrality(dumbbell, "betweenness"), 2))).toEqual(["c", "d"]);
    const star = graph("x-a x-b x-c x-d");
    for (const by of ["degree", "betweenness", "pagerank", "closeness"] as const) expect([...top(centrality(star, by), 1)]).toEqual(["x"]);
    // betweenness of a star's centre: every pair of leaves goes through it, 4 choose 2
    expect(centrality(star, "betweenness").get("x")).toBe(6);
  });

  it("communities: the two triangles, largest first", () => {
    const c = communities(graph("a-b b-c c-a d-e e-f f-d c-d"));
    expect(c.get("a")).toBe(c.get("b"));
    expect(c.get("a")).toBe(c.get("c"));
    expect(c.get("d")).toBe(c.get("e"));
    expect(c.get("a")).not.toBe(c.get("d"));
    expect(new Set(c.values())).toEqual(new Set([0, 1]));
  });

  it("within: only the links between the pages kept", () => {
    expect(sorted(within(dumbbell, ["a", "b", "g"]).get("a")!)).toEqual(["b"]);
    expect(within(dumbbell, ["a", "b", "g"]).get("g")!.size).toBe(0);
  });
});

describe("sampling above SAMPLE_ABOVE pages", () => {
  it("a sampled betweenness still finds the centre of a large star", () => {
    const edges = Array.from({ length: 900 }, (_, i) => `hub-p${String(i).padStart(3, "0")}`).join(" ");
    const big = graph(edges);
    expect([...top(centrality(big, "betweenness"), 1)]).toEqual(["hub"]);
    expect([...top(centrality(big, "closeness"), 1)]).toEqual(["hub"]);
  });
});
