import { node, sampleLinks, sampleNodes } from "../fixtures";
import type { ViewSpecV1 } from "../shell/corners/viewSpec";
import { QUICK_OFF } from "../quickFilters";
import { describe as words, evaluate, fromViewSpecV1, legendRows, makeLayer, mainParam, remove, replace, stack, update, withParam, EMPTY_STACK, type Layer } from "./model";

const show = (text: string, nodes: Layer["subgraph"]["nodes"] = [], id?: string): Layer => ({ ...makeLayer("show", "nodes", { nodes }, text), ...(id ? { id } : {}) });
const hide = (text: string, nodes: Layer["subgraph"]["nodes"] = []): Layer => makeLayer("hide", "nodes", { nodes }, text);
const color = (by: "area" | "depth", text = ""): Layer => makeLayer("style", "nodes", {}, text, { style: { color: by } });
const graph = { nodes: sampleNodes, links: sampleLinks };

describe("stack operations", () => {
  it("replace keeps the style layers and swaps the show and hide ones", () => {
    const s0 = stack(stack(EMPTY_STACK, [show("old show"), hide("old hide")]), [color("area", "colour by area")]);
    const s1 = replace(s0, [show("new show")]);
    expect(s1.layers.map((l) => l.text)).toEqual(["colour by area", "new show"]);
    expect(s0.layers).toHaveLength(3);
  });

  it("stack appends in order, later last", () => {
    const s = stack(stack(EMPTY_STACK, [show("a")]), [hide("b")]);
    expect(s.layers.map((l) => l.text)).toEqual(["a", "b"]);
  });

  it("remove drops the first layer whose text or id matches, and returns the same stack when none does", () => {
    const a = show("only papers");
    const s = stack(EMPTY_STACK, [a, show("only papers"), hide("hide people")]);
    expect(remove(s, "Only Papers").layers.map((l) => l.id)).toEqual([s.layers[1]!.id, s.layers[2]!.id]);
    expect(remove(s, a.id).layers).toHaveLength(2);
    expect(remove(s, "nothing like it")).toBe(s);
  });

  it("update changes one layer where it stands", () => {
    const s = stack(EMPTY_STACK, [show("a"), show("b")]);
    const next = update(s, s.layers[0]!.id, { ...s.layers[0]!, text: "z" });
    expect(next.layers.map((l) => l.text)).toEqual(["z", "b"]);
  });

  it("describes a layer in plain words when it has no text", () => {
    expect(words(makeLayer("show", "nodes", { nodes: [{ t: "type", value: "paper" }, { t: "hops", of: "idea-margin", n: 2 }] }))).toBe("Show pages: type paper, within 2 hops of idea-margin");
    expect(words(makeLayer("hide", "edges", { edges: [{ t: "type", value: "MENTIONS" }] }))).toBe("Hide links: MENTIONS links");
    expect(words(color("area"))).toBe("Style pages: colour area");
    expect(words(show("my words"))).toBe("my words");
  });
});

describe("evaluate", () => {
  const ids = (l: Layer[]) => evaluate(stack(EMPTY_STACK, l), graph).nodeIds;

  it("an empty stack restricts nothing", () => {
    const ev = evaluate(EMPTY_STACK, graph);
    expect(ev.nodeIds).toBeNull();
    expect(ev.hiddenLinkKinds.size).toBe(0);
    expect(ev.skipped).toEqual([]);
  });

  it("show by type, and hide takes pages out of everything", () => {
    expect([...ids([show("papers", [{ t: "type", value: "paper" }])])!].sort()).toEqual(["2019-fine-grained", "2020-listed-paper"]);
    const ev = evaluate(stack(EMPTY_STACK, [hide("people", [{ t: "type", value: "person" }])]), graph);
    expect(ev.nodeIds!.has("jane-doe")).toBe(false);
    expect(ev.nodeIds!.size).toBe(sampleNodes.length - 1);
  });

  it("degree counts the distinct pages a page is linked with", () => {
    const connected = ids([show("connected", [{ t: "degree", op: ">=", n: 2 }])]);
    expect([...connected!].sort()).toEqual(["2019-fine-grained", "idea-margin", "topic-learning-theory"]);
    const orphans = ids([show("none", [{ t: "degree", op: "=", n: 0 }])]);
    expect(orphans!.size).toBe(0);
  });

  it("hops walks the links in either direction", () => {
    expect([...ids([show("h1", [{ t: "hops", of: "course-runi-rl", n: 1 }])])!].sort()).toEqual(["2019-fine-grained", "course-runi-rl"]);
    const two = ids([show("h2", [{ t: "hops", of: "course-runi-rl", n: 2 }])])!;
    expect([...two].sort()).toEqual(["2019-fine-grained", "course-runi-rl", "idea-margin", "topic-learning-theory"]);
    const none = evaluate(stack(EMPTY_STACK, [show("x", [{ t: "hops", of: "no-such-page", n: 2 }])]), graph);
    expect(none.skipped[0]).toMatch(/no-such-page/);
  });

  it("conditions of one subgraph all hold", () => {
    expect([...ids([show("both", [{ t: "type", value: "idea" }, { t: "degree", op: ">=", n: 3 }])])!]).toEqual(["idea-margin"]);
  });

  it("the order matters: a later layer wins", () => {
    const papers = show("papers", [{ t: "type", value: "paper" }]);
    const listed = hide("listed", [{ t: "name", slugs: ["2020-listed-paper"] }]);
    expect([...ids([papers, listed])!]).toEqual(["2019-fine-grained"]);
    expect(ids([listed, papers])!.has("2020-listed-paper")).toBe(true);
  });

  it("a later show adds to the earlier one", () => {
    expect(ids([show("a", [{ t: "name", slugs: ["jane-doe"] }]), show("b", [{ t: "name", slugs: ["idea-margin"] }])])!.size).toBe(2);
  });

  it("hides link kinds, mapping the graph's names onto the canvas kinds", () => {
    const ev = evaluate(stack(EMPTY_STACK, [makeLayer("hide", "edges", { edges: [{ t: "type", value: "MENTIONS" }] })]), graph);
    expect([...ev.hiddenLinkKinds].sort()).toEqual(["related", "wikilink"]);
    expect(ev.legend).toHaveLength(1);
    const odd = evaluate(stack(EMPTY_STACK, [makeLayer("hide", "edges", { edges: [{ t: "type", value: "contradicts" }] })]), graph);
    expect(odd.hiddenLinkKinds.size).toBe(0);
    expect(odd.skipped[0]).toMatch(/contradicts/);
  });

  it("show edges of a type hides the other kinds", () => {
    const ev = evaluate(stack(EMPTY_STACK, [makeLayer("show", "edges", { edges: [{ t: "type", value: "related" }] })]), graph);
    expect([...ev.hiddenLinkKinds]).toEqual(["wikilink"]);
  });

  it("folds style layers into the knobs", () => {
    const ev = evaluate(stack(EMPTY_STACK, [color("depth"), makeLayer("style", "nodes", {}, "", { style: { size: { by: "degree" }, color: { by: "areas" } } })]), graph);
    expect(ev.patch).toEqual({ colorBy: "area", sizeBy: "connections" });
    expect(ev.legend.map((r) => r.group)).toEqual(["pages", "pages"]);
  });

  it("lists what it cannot evaluate yet, never dropping it silently", () => {
    const ev = evaluate(stack(EMPTY_STACK, [show("x", [{ t: "about", phrase: "margins" }, { t: "text", phrase: "kernel" }, { t: "favorite" }, { t: "type", value: "idea" }])]), graph);
    expect(ev.nodeIds).toEqual(new Set(["idea-margin"]));
    expect(ev.skipped).toHaveLength(3);
    expect(ev.skipped.join("|")).toMatch(/about "margins"/);
    expect(ev.skipped.join("|")).toMatch(/favorites/);
  });

  it("favorites and age evaluate when the graph carries them", () => {
    const g = { nodes: [node("a", { added: "2026-11-01" }), node("b", { added: "2020-01-01" })], links: [], favorites: new Set(["b"]), now: Date.parse("2026-11-06") };
    expect([...evaluate(stack(EMPTY_STACK, [show("f", [{ t: "favorite" }])]), g).nodeIds!]).toEqual(["b"]);
    expect([...evaluate(stack(EMPTY_STACK, [show("r", [{ t: "createdWithin", days: 30 }])]), g).nodeIds!]).toEqual(["a"]);
  });

  it("linkedFromType and area", () => {
    expect([...ids([show("l", [{ t: "linkedFromType", type: "question" }])])!]).toEqual(["topic-learning-theory"]);
    expect(ids([show("a", [{ t: "inArea", area: "optimization-theory" }])])!.has("idea-margin")).toBe(true);
  });
});

describe("chips parameters", () => {
  it("reads and writes a layer's main parameter and rewrites its words", () => {
    const l = makeLayer("show", "nodes", { nodes: [{ t: "type", value: "idea" }, { t: "hops", of: "x", n: 3 }] });
    expect(mainParam(l)).toEqual({ kind: "hops", n: 3 });
    expect(words(withParam(l, { kind: "hops", n: 2 }))).toBe("Show pages: type idea, within 2 hops of x");
    const e = makeLayer("hide", "edges", { edges: [{ t: "type", value: "a" }] });
    expect(words(withParam(e, { kind: "edgeType", value: "b" }))).toBe("Hide links: b links");
    expect(mainParam(color("area"))).toEqual({ kind: "color", value: "area" });
    expect(mainParam(show("plain"))).toBeNull();
  });

  it("legend rows come from style layers and link layers", () => {
    const s = stack(EMPTY_STACK, [show("a"), color("area", "colour by area"), makeLayer("hide", "edges", { edges: [{ t: "type", value: "x" }] })]);
    expect(legendRows(s).map((r) => [r.group, r.label])).toEqual([["pages", "colour by area"], ["links", "Hide links: x links"]]);
  });
});

describe("fromViewSpecV1", () => {
  it("is one show layer named after the view, carrying the V1 spec", () => {
    const spec: ViewSpecV1 = { v: 1, story: "map", colorBy: "type", sizeBy: "tier", types: "default", depths: null, hiddenKeys: [], quick: QUICK_OFF };
    const s = fromViewSpecV1(spec, "Contradictions");
    expect(s.v).toBe(2);
    expect(s.layers).toHaveLength(1);
    expect(s.layers[0]).toMatchObject({ kind: "show", target: "nodes", text: "Contradictions", legacy: spec });
    expect(evaluate(s, graph).nodeIds).toBeNull();
  });
});
