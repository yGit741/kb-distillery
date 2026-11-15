import { withFlag } from "@/flags/testing";
import { node } from "../fixtures";
import { parse, print } from "./grammar";
import { isParseError } from "./grammar";
import { components, EMPTY_STACK, evaluate, makeLayer, shortestPaths, stack, type Layer } from "./model";
import { fromSentence } from "./sentence";

/*
 * a - b - c - d     a square with a tail: two shortest paths a..c (via b and via e),
 * a - e - c         one component of five, and an island f - g
 * f - g
 */
const ids = ["a", "b", "c", "d", "e", "f", "g"];
const links = [
  ["a", "b"], ["b", "c"], ["c", "d"], ["a", "e"], ["e", "c"], ["f", "g"],
].map(([source, target]) => ({ source: source!, target: target!, kind: "wikilink" as const }));
const graph = { nodes: ids.map((id) => node(id, { title: id.toUpperCase() })), links };
const adj = new Map<string, Set<string>>();
for (const l of links) {
  (adj.get(l.source) ?? adj.set(l.source, new Set()).get(l.source)!).add(l.target);
  (adj.get(l.target) ?? adj.set(l.target, new Set()).get(l.target)!).add(l.source);
}
const run = (layers: Layer[], drawn?: Set<string>) => [...(evaluate(stack(EMPTY_STACK, layers), { ...graph, drawn }).nodeIds ?? [])].sort();

describe("graph algorithms", () => {
  it("shortest paths: one, or all of the same length", () => {
    expect([...shortestPaths(adj, "a", "c")].sort()).toHaveLength(3);
    expect([...shortestPaths(adj, "a", "c", true)].sort()).toEqual(["a", "b", "c", "e"]);
    expect([...shortestPaths(adj, "a", "d")]).toContain("d");
    expect(shortestPaths(adj, "a", "f").size).toBe(0);
  });

  it("components, largest first", () => {
    expect(components(adj, ids).map((c) => c.sort())).toEqual([["a", "b", "c", "d", "e"], ["f", "g"]]);
    // as drawn: hide c and the square falls apart
    expect(components(adj, ids.filter((i) => i !== "c")).map((c) => c.length)).toEqual([3, 2, 1]);
  });
});

describe("flag graph-algos: graph-theory words in a > line", () => {
  it("on: shortest paths, common neighbours, components, expand and deg", () =>
    withFlag("graph-algos", true, async () => {
      expect(fromSentence("shortest path from A to D").lines).toEqual(['show nodes shortest path between "A" and "D"']);
      expect(fromSentence("all shortest paths between A and C").lines).toEqual(['show nodes all shortest paths between "A" and "C"']);
      expect(fromSentence("common neighbours of B and E").lines).toEqual(['show nodes common neighbours of "B" and "E"']);
      expect(fromSentence("largest component").lines).toEqual(["show nodes largest component"]);
      expect(fromSentence("component of F").lines).toEqual(['show nodes component of "F"']);
      expect(fromSentence("show only deg>4 and their neighbors").lines).toEqual(["show nodes degree > 4 expand 1"]);
      expect(fromSentence("deg >= 2").lines).toEqual(["show nodes degree >= 2"]);
      expect(fromSentence("hubs +2 hops").lines).toEqual(["show nodes degree >= 8 expand 2"]);
    }));

  it("on: the words draw the right pages", () =>
    withFlag("graph-algos", true, async () => {
      const read = (t: string) => fromSentence(t).layers;
      expect(run(read("all shortest paths between A and C"))).toEqual(["a", "b", "c", "e"]);
      expect(run(read("common neighbours of B and E"))).toEqual(["a", "c"]);
      expect(run(read("largest component"))).toEqual(["a", "b", "c", "d", "e"]);
      expect(run(read("component of G"))).toEqual(["f", "g"]);
      // c has degree 3; with its neighbours: b, d, e
      expect(run(read("deg>2 and their neighbours"))).toEqual(["b", "c", "d", "e"]);
      // as drawn: expanding steps only onto drawn pages (e hidden: a's neighbours are b, then c)
      const fromA: Layer = { ...makeLayer("show", "nodes", { nodes: [{ t: "name", slugs: ["a"] }] }), expand: 2 };
      expect(run([fromA], new Set(ids.filter((i) => i !== "e")))).toEqual(["a", "b", "c"]);
      expect(run([fromA])).toEqual(["a", "b", "c", "e"]);
    }));

  it("on: a path and its neighbours; a name that is no page answers nothing, never every page", () =>
    withFlag("graph-algos", true, async () => {
      expect(fromSentence("shortest path from A to D and their neighbours").lines).toEqual(['show nodes shortest path between "A" and "D" expand 1']);
      const read = (t: string) => fromSentence(t).layers;
      expect(run(read("shortest path from A to Zzz"))).toEqual([]);
      // a hide of a skipped condition hides nothing
      expect(run([{ ...read("common neighbours of A and Zzz")[0]!, kind: "hide" }])).toEqual(ids);
    }));

  it("on: components count what is drawn; one not drawn, or past the last, answers nothing", () =>
    withFlag("graph-algos", true, async () => {
      const read = (t: string) => fromSentence(t).layers;
      const noC = new Set(ids.filter((i) => i !== "c"));
      expect(run(read("component of C"), noC)).toEqual([]);
      expect(run([makeLayer("show", "nodes", { nodes: [{ t: "component", rank: 9 }] })], noC)).toEqual([]);
    }));

  it("a bare degree counts drawn pages only; with a page type it may reach a hidden type", () => {
    const g = { nodes: [node("p1", { type: "paper" }), node("p2", { type: "paper" }), node("i1", { type: "idea" }), node("i2", { type: "idea" })], links: [
      { source: "p1", target: "p2", kind: "wikilink" as const }, { source: "i1", target: "i2", kind: "wikilink" as const }, { source: "p1", target: "i1", kind: "wikilink" as const },
    ] };
    const drawn = new Set(["i1", "i2"]);
    const ev = (conds: Layer["subgraph"]["nodes"]) => [...evaluate(stack(EMPTY_STACK, [makeLayer("show", "nodes", { nodes: conds })]), { ...g, drawn }).nodeIds!].sort();
    expect(ev([{ t: "degree", op: ">=", n: 1 }])).toEqual(["i1", "i2"]);
    expect(ev([{ t: "type", value: "paper" }, { t: "degree", op: ">=", n: 2 }])).toEqual(["p1"]);
  });

  it("off: the words are not read by the rules (they go to the model as before)", () =>
    withFlag("graph-algos", false, async () => {
      for (const t of ["shortest path from A to D", "common neighbours of B and E", "largest component", "show only deg>4 and their neighbors"])
        expect(fromSentence(t).unknown, t).toBe(t);
    }));
});

describe("the language lines", () => {
  it("print and parse round trip", () => {
    for (const line of [
      'show nodes shortest path between "A" and "D"',
      'show nodes all shortest paths between "A" and "C"',
      'show nodes common neighbours of "B" and "E"',
      "show nodes largest component",
      "show nodes component 2",
      'show nodes component of "F"',
      "show nodes degree > 4 expand 1",
      "hide nodes degree = 0 expand 2",
    ]) {
      const l = parse(line);
      expect(isParseError(l), line).toBe(false);
      expect(print(l as Layer)).toBe(line);
    }
  });
});
