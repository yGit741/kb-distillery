import { node } from "@/features/graph/fixtures";
import type { GNode } from "@/features/graph/types";
import { parseCards } from "./curated";
import { radii } from "./SampleGraph";
import { MAX_LINKS, MAX_NODES, MIN_NODES, RANDOM_ORDER, SAMPLERS, curated, graphSearch, indexVault, neighbourhood, rng, sampleAll } from "./samplers";

// a hub topic with 30 digested papers, an open question, a bridge idea between two areas, and listed stubs
const papers = Array.from({ length: 30 }, (_, i) =>
  node(`p${i}`, { type: "paper", layer: "source", depth: i % 3 ? "easy" : "full", status: "digested", year: 2000 + i, areas: [i % 2 ? "info-theory" : "learning-theory"] }),
);
const nodes: GNode[] = [
  node("theme-a", { areas: ["learning-theory"] }),
  node("theme-b", { areas: ["info-theory"] }),
  node("bridge-idea", { type: "idea", areas: ["learning-theory", "info-theory"] }),
  node("q-open", { type: "question", status: "open" }),
  node("thin-idea", { type: "idea" }),
  node("stub", { type: "paper", layer: "source", depth: "listed", status: "to-read" }),
  ...papers,
];
const links = [
  ...papers.map((p) => ({ source: p.id, target: Number(p.id.slice(1)) % 2 ? "theme-b" : "theme-a" })),
  { source: "bridge-idea", target: "theme-a" },
  { source: "bridge-idea", target: "theme-b" },
  { source: "bridge-idea", target: "p1" },
  { source: "q-open", target: "p2" },
  { source: "q-open", target: "p3" },
  { source: "q-open", target: "bridge-idea" },
  { source: "thin-idea", target: "theme-a" },
  { source: "thin-idea", target: "theme-b" },
  { source: "thin-idea", target: "p4" },
  { source: "stub", target: "theme-a" },
  { source: "stub", target: "q-open" },
];
const vault = indexVault(nodes, links);

describe("home samplers", () => {
  it("never draws listed stubs", () => {
    expect(vault.eligible.has("stub")).toBe(false);
    for (const s of sampleAll(vault, {})) expect(s.nodes).not.toContain("stub");
  });

  it("is deterministic per seed and changes with it", () => {
    const a = SAMPLERS.random(vault, rng(7));
    expect(SAMPLERS.random(vault, rng(7))).toEqual(a);
    const foci = new Set(Array.from({ length: 20 }, (_, i) => SAMPLERS.random(vault, rng(i + 1))?.focus));
    expect(foci.size).toBeGreaterThan(1);
  });

  it("caps nodes and links, and keeps the focus", () => {
    const hub = neighbourhood(vault, "theme-a");
    expect(hub.nodes.length).toBe(MAX_NODES);
    expect(hub.nodes[0]).toBe("theme-a");
    expect(hub.links.length).toBeLessThanOrEqual(MAX_LINKS);
    for (const [a, b] of hub.links) expect(hub.nodes.includes(a) && hub.nodes.includes(b)).toBe(true);
  });

  it("gives every kind a card with at least MIN_NODES pages", () => {
    const all = sampleAll(vault, { random: 3, bridge: 3, question: 3, newest: 3, thin: 3 });
    expect(all.map((s) => s.kind)).toEqual([...RANDOM_ORDER]);
    for (const s of all) expect(s.nodes.length).toBeGreaterThanOrEqual(MIN_NODES);
    expect(all.find((s) => s.kind === "question")?.focus).toBe("q-open");
    expect(all.find((s) => s.kind === "thin")?.focus).toBe("thin-idea");
    expect(all.find((s) => s.kind === "bridge")?.focus).toMatch(/^(bridge-idea|theme-a|theme-b|q-open|thin-idea)$/);
  });

  it("drops a kind with nothing to show instead of showing an empty card", () => {
    const tiny = indexVault([node("a"), node("b")], [{ source: "a", target: "b" }]);
    expect(sampleAll(tiny, {})).toEqual([]);
  });

  it("curated cards keep pages present in the build and fall back to the focus's neighbourhood", () => {
    const full = curated(vault, { title: "T", pages: ["theme-a", "p0", "p2", "gone"], focus: "p0", caption: "c" });
    expect(full).toMatchObject({ kind: "curated", title: "T", focus: "p0", caption: "c" });
    expect(full?.nodes).toEqual(["p0", "theme-a", "p2"]);
    const grown = curated(vault, { title: "T", pages: ["q-open"] });
    expect(grown?.nodes.length).toBeGreaterThanOrEqual(MIN_NODES);
    expect(curated(vault, { title: "T", pages: ["gone", "stub"] })).toBeNull();
  });

  it("links to the full graph with the subset selected and focused", () => {
    expect(graphSearch({ nodes: ["a", "b"], focus: "a" })).toEqual({ pages: "a,b", select: "a", focus: "a" });
    expect(graphSearch({ nodes: ["a", "b"], focus: "a" }, "b")).toEqual({ pages: "a,b", select: "b", focus: "b" });
  });

  it("sizes nodes 3-7 px by degree inside the sample", () => {
    const r = radii({ nodes: ["a", "b", "c"], links: [["a", "b"], ["a", "c"]] });
    expect(r.get("a")).toBe(7);
    expect(r.get("b")).toBe(5);
  });

  it("parses profile cards and drops malformed ones", () => {
    expect(parseCards([{ title: "x", pages: ["a", 3, ""], focus: "a" }, { title: "", pages: ["a"] }, { pages: [] }, null, "s"])).toEqual([
      { title: "x", pages: ["a"], focus: "a", caption: undefined },
    ]);
    expect(parseCards(undefined)).toEqual([]);
  });
});
