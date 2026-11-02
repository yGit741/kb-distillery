import { node } from "@/features/graph/fixtures";
import type { GNode } from "@/features/graph/types";
import { parseCards } from "./curated";
import { R_MAX, R_MIN, radii } from "./SampleGraph";
import {
  MAX_LINKS,
  MAX_NODES,
  MIN_NODES,
  NODE_NEIGHBOURS,
  RANDOM_ORDER,
  SAMPLERS,
  curated,
  excerpt,
  graphSearch,
  indexVault,
  neighbourhood,
  rng,
  sampleAll,
  sampleNode,
  sampleNodes,
  pickSource,
  conceptsFed,
  egoSample,
  drawPickable,
} from "./samplers";

// a hub topic with 30 digested papers, an open question, a bridge idea between two areas, and listed stubs
const papers = Array.from({ length: 30 }, (_, i) =>
  node(`p${i}`, { type: "paper", layer: "source", depth: i % 3 ? "easy" : "full", maturity: "digested", year: 2000 + i, areas: [i % 2 ? "info-theory" : "learning-theory"] }),
);
const nodes: GNode[] = [
  node("theme-a", { areas: ["learning-theory"] }),
  node("theme-b", { areas: ["info-theory"] }),
  node("bridge-idea", { type: "idea", areas: ["learning-theory", "info-theory"] }),
  node("q-open", { type: "question", maturity: "open" }),
  node("thin-idea", { type: "idea" }),
  node("stub", { type: "paper", layer: "source", depth: "listed", maturity: "to-read" }),
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
    // the drawn source is selected next to the concept; one outside the sample is ignored
    expect(graphSearch({ nodes: ["a", "b", "s"], focus: "a" }, "a", "s")).toEqual({ pages: "a,b,s", select: "a,s", focus: "a" });
    expect(graphSearch({ nodes: ["a", "b"], focus: "a" }, "a", "zz")).toEqual({ pages: "a,b", select: "a", focus: "a" });
  });

  it("sizes nodes R_MIN-R_MAX screen px by degree inside the sample", () => {
    const r = radii({ nodes: ["a", "b", "c"], links: [["a", "b"], ["a", "c"]] });
    expect(r.get("a")).toBe(R_MAX);
    expect(r.get("b")).toBe((R_MIN + R_MAX) / 2);
  });

  it("samples one knowledge node per kind with its best neighbours, never a stub", () => {
    const all = sampleNodes(vault, { idea: 2, source: 2, question: 2 });
    expect(all.map((s) => s.kind)).toEqual(["idea", "source", "question"]);
    expect(["bridge-idea", "thin-idea", "theme-a", "theme-b"]).toContain(all[0]?.id);
    expect(vault.byId.get(all[1]!.id)?.layer).toBe("source");
    expect(all[2]?.id).toBe("q-open");
    for (const s of all) {
      expect(s.neighbours).not.toContain("stub");
      expect(s.neighbours.length).toBeLessThanOrEqual(NODE_NEIGHBOURS);
    }
    expect(sampleNode(vault, "idea", rng(5))).toEqual(sampleNode(vault, "idea", rng(5)));
  });

  it("excerpts the opening of a page without title, front matter or My notes", () => {
    const md = "---\ntype: idea\n---\n# AdamW\n\n**One-liner:** Adam with decoupled decay.\n\n## Intuition\n\nShrink weights.\n\n## My notes\n\nprivate";
    const ex = excerpt(md);
    expect(ex).toContain("One-liner");
    expect(ex).toContain("Shrink weights.");
    expect(ex).not.toMatch(/# AdamW|type: idea|private|My notes/);
    expect(excerpt("# T\n\n" + "a".repeat(900) + "\n\nsecond")).toBe("a".repeat(900));
    expect(excerpt("| a | b |\n|---|---|\n| 1 | 2 |\n\nProse.")).toBe("Prose.");
    expect(excerpt("**Question:** Why is it so?\n\nBecause.", undefined, "Why is it so?")).toBe("Because.");
  });

  it("keeps every card connected to its focus under the link cap", () => {
    const hub = neighbourhood(vault, "theme-a");
    for (const id of hub.nodes.slice(1)) expect(hub.links.some(([a, b]) => (a === "theme-a" && b === id) || (b === "theme-a" && a === id))).toBe(true);
  });

  it("parses profile cards and drops malformed ones", () => {
    expect(parseCards([{ title: "x", pages: ["a", 3, ""], focus: "a" }, { title: "", pages: ["a"] }, { pages: [] }, null, "s"])).toEqual([
      { title: "x", pages: ["a"], focus: "a", caption: undefined },
    ]);
    expect(parseCards(undefined)).toEqual([]);
  });
});

describe("intro card: pick a concept, draw a source", () => {
  const raw = (path: string) => ({ properties: { raw: path } }) as Partial<GNode>;
  const g = indexVault(
    [
      node("idea-x", { type: "idea" }),
      node("idea-y", { type: "idea" }),
      node("q-far", { type: "question", maturity: "open" }),
      node("topic-none", { type: "topic" }),
      node("s-deep-clip", { type: "article", layer: "source", depth: "deep", ...raw("raw/web-clips/a.md") }),
      node("s-full-pdf", { type: "paper", layer: "source", depth: "full", ...raw("raw/printed-docs/b.pdf") }),
      node("s-easy", { type: "paper", layer: "source", depth: "easy" }),
      node("s-listed", { type: "paper", layer: "source", depth: "listed" }),
      node("s-easy-2", { type: "paper", layer: "source", depth: "easy" }),
    ],
    [
      { source: "s-deep-clip", target: "idea-x" },
      { source: "s-full-pdf", target: "idea-x" },
      { source: "s-easy", target: "idea-x" },
      { source: "q-far", target: "idea-y" },
      { source: "s-easy-2", target: "idea-y" },
      { source: "s-listed", target: "idea-y" },
    ],
  );

  it("draws a direct source from the best tier, PDFs first", () => {
    for (let seed = 1; seed < 20; seed++) expect(pickSource(g, "idea-x", rng(seed))).toEqual({ id: "s-full-pdf", via: null });
  });
  it("falls back to a source two hops away through an idea", () => {
    expect(pickSource(g, "q-far", rng(3))).toEqual({ id: "s-easy-2", via: "idea-y" });
  });
  it("public builds keep only full/deep sources; no source at all is null", () => {
    expect(pickSource(g, "q-far", rng(3), true)).toBeNull();
    expect(pickSource(g, "topic-none", rng(3))).toBeNull();
  });
  it("lists the concepts a source feeds, the picked one first", () => {
    expect(conceptsFed(g, "s-easy-2", "idea-y")).toEqual(["idea-y"]);
  });
  it("the ego sample keeps the concept, the drawn source and its idea, joined", () => {
    const s = egoSample(g, "q-far", { id: "s-listed", via: "idea-y" });
    expect(s.focus).toBe("q-far");
    expect(s.nodes).toEqual(expect.arrayContaining(["q-far", "s-listed", "idea-y"]));
    expect(s.links).toEqual(expect.arrayContaining([["idea-y", "s-listed"]]));
  });
  it("the shuffle only lands on topics, ideas and questions", () => {
    for (let seed = 1; seed < 10; seed++) expect(["topic", "idea", "question"]).toContain(vault.byId.get(drawPickable(vault, rng(seed)) ?? "")?.type);
  });
});
