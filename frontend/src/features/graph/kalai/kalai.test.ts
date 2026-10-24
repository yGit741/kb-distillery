import { describe, expect, it } from "vitest";
import { node } from "../fixtures";
import type { GLink, GNode, GraphModel } from "../types";
import { louvain, pageGraph, pagerank, rng, themesOf } from "./core";
import { notablePairs, spectrum } from "./fourier";
import { clusterJaccard, noiseStability } from "./noise";
import { heldAt, thresholds } from "./threshold";

const topic = (t: string) => node(`theme-${t}`, { type: "topic", areas: [t] });
const page = (id: string, areas: string[], o: Partial<GNode> = {}) => node(id, { type: "paper", layer: "source", depth: "listed", areas, ...o });
const link = (source: string, target: string): GLink => ({ source, target, kind: "wikilink" });

/** Two cliques of 6 (themes a and b), joined by one bridge; a third theme c that never meets b. */
function twoCliques(): GraphModel {
  const nodes: GNode[] = [topic("a"), topic("b"), topic("c")];
  const links: GLink[] = [];
  for (const side of ["a", "b"]) {
    const ids = Array.from({ length: 6 }, (_, i) => `${side}${i}`);
    ids.forEach((id, i) => nodes.push(page(id, i < 2 && side === "a" ? ["a", "c"] : [side], { depth: i === 0 && side === "a" ? "full" : "listed" })));
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) links.push(link(ids[i] as string, ids[j] as string));
  }
  links.push(link("a5", "b5"));
  return { nodes, links, conceptLinks: [] };
}

describe("core", () => {
  it("rng is reproducible", () => {
    const a = rng(3);
    const b = rng(3);
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });

  it("themes come from the topic pages, and hubs are left out of the page graph", () => {
    const m = twoCliques();
    expect(themesOf(m.nodes)).toEqual(["a", "b", "c"]);
    expect(pageGraph(m).ids).not.toContain("theme-a");
    expect(pageGraph(m, { hubs: true }).ids).toContain("theme-a");
  });

  it("louvain splits two cliques joined by one bridge", () => {
    const g = pageGraph(twoCliques());
    const c = louvain(g.ids.length, g.edges);
    const of = (id: string) => c[g.index.get(id) as number];
    expect(of("a0")).toBe(of("a4"));
    expect(of("b0")).toBe(of("b4"));
    expect(of("a0")).not.toBe(of("b0"));
  });

  it("pagerank sums to one and favours the bridge ends", () => {
    const g = pageGraph(twoCliques());
    const pr = pagerank(g.ids.length, g.edges);
    expect(pr.reduce((s, v) => s + v, 0)).toBeCloseTo(1, 6);
    expect(pr[g.index.get("a5") as number]).toBeGreaterThan(pr[g.index.get("a1") as number] as number);
  });
});

describe("fourier", () => {
  it("finds the over-represented pair and the gap", () => {
    const s = spectrum(twoCliques(), { nullRuns: 4 });
    const ac = s.pairs.find((p) => p.a === "a" && p.b === "c");
    const bc = s.pairs.find((p) => p.a === "b" && p.b === "c");
    expect(ac?.both).toBe(2);
    expect(ac?.coef).toBeGreaterThan(0);
    expect(bc?.both).toBe(0);
    expect(bc?.coef).toBeLessThan(0);
    expect(notablePairs(s).over.map((p) => `${p.a}${p.b}`)).toContain("ac");
  });

  it("a theme on every themed page carries no information; the level-2 coefficient is the correlation", () => {
    const nodes = [topic("x"), topic("y"), ...["p1", "p2", "p3", "p4"].map((id, i) => page(id, i < 2 ? ["x", "y"] : []))];
    expect(spectrum({ nodes, links: [], conceptLinks: [] }, { nullRuns: 2 }).themes).toEqual([]);
    const nodes2 = [topic("x"), topic("y"), page("p1", ["x", "y"]), page("p2", ["x", "y"]), page("p3", ["x"]), page("p4", ["y"])];
    const s2 = spectrum({ nodes: nodes2, links: [], conceptLinks: [] }, { nullRuns: 2 });
    expect(s2.pairs[0]?.coef).toBeCloseTo(-1 / 3, 6);
  });

  it("infers themes for an untagged page from its tagged neighbours", () => {
    const base = twoCliques();
    const m: GraphModel = { ...base, nodes: [...base.nodes, page("orphan", [])], links: [...base.links, link("orphan", "b1"), link("orphan", "b2")] };
    expect(spectrum(m, { infer: false, nullRuns: 1 }).inferred).toBe(0);
    const s = spectrum(m, { infer: true, nullRuns: 1 });
    expect(s.inferred).toBe(1);
    expect(s.members.get("b")).toContain("orphan");
  });

  it("attention: the theme of the deeply read page predicts deep reading", () => {
    const s = spectrum(twoCliques(), { nullRuns: 1, minSupport: 1 });
    const a = s.attention.find((x) => x.set.join() === "a");
    const b = s.attention.find((x) => x.set.join() === "b");
    expect((a?.rate ?? 0) > (b?.rate ?? 0)).toBe(true);
  });
});

describe("noise", () => {
  it("per-page Jaccard is 1 for equal partitions and drops when a page moves", () => {
    const base = Int32Array.from([0, 0, 1, 1]);
    expect([...clusterJaccard(base, Int32Array.from([5, 5, 7, 7]))]).toEqual([1, 1, 1, 1]);
    const moved = clusterJaccard(base, Int32Array.from([0, 1, 1, 1]));
    expect(moved[0]).toBe(0.5);
    expect(moved[2]).toBeCloseTo(2 / 3);
  });

  it("is perfectly stable at zero noise and reproducible", async () => {
    const m = twoCliques();
    const r0 = await noiseStability(m, { eps: 0, runs: 2, conceptsOnly: false });
    expect(r0.meanStability).toBe(1);
    expect(r0.meanTopKeep).toBe(1);
    const a = await noiseStability(m, { eps: 0.3, runs: 3, conceptsOnly: false });
    const b = await noiseStability(m, { eps: 0.3, runs: 3, conceptsOnly: false });
    expect([...a.clusterStability]).toEqual([...b.clusterStability]);
  });
});

describe("threshold", () => {
  it("cohesion curves are monotone, 0 at p=0 and 1 at p=1 for a connected theme", () => {
    const r = thresholds(twoCliques(), { draws: 40 });
    const a = r.pairs.find((x) => x.a === "a" && x.b === "a");
    expect(a).toBeDefined();
    if (!a) return;
    expect(heldAt(a, 0)).toBe(0);
    expect(heldAt(a, 1)).toBe(1);
    let prev = 0;
    for (let p = 0; p <= 1; p += 0.05) {
      expect(heldAt(a, p)).toBeGreaterThanOrEqual(prev);
      prev = heldAt(a, p);
    }
  });

  it("joining two themes over one bridge needs more links than either theme alone", () => {
    const r = thresholds(twoCliques(), { draws: 80 });
    const own = (t: string) => r.pairs.find((x) => x.a === t && x.b === t)?.p50 ?? 0;
    const ab = r.pairs.find((x) => x.a === "a" && x.b === "b");
    expect(ab?.p50).toBeGreaterThan(Math.max(own("a"), own("b")));
    expect(ab?.bridge).not.toBeNull();
    expect(r.giant[0]?.share).toBeLessThan(r.giant[50]?.share as number);
  });

  it("weighting keeps well-backed links earlier", () => {
    const m = twoCliques();
    m.conceptLinks = [{ source: "a0", target: "b0", shared: 8 }];
    const plain = thresholds(m, { draws: 60 }).pairs.find((x) => x.a === "a" && x.b === "b");
    const weighted = thresholds(m, { draws: 60, weighted: true }).pairs.find((x) => x.a === "a" && x.b === "b");
    expect(weighted?.p50).toBeLessThan(plain?.p50 as number);
  });
});
