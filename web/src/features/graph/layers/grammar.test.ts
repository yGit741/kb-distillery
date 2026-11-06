import { isParseError, parse, print } from "./grammar";
import { FAVORITES, FOCUS, makeLayer, type Layer } from "./model";
import { fromSentence } from "./sentence";
import { SENTENCES } from "./sentence.fixtures";

const noId = (l: Layer) => ({ ...l, id: "" });
const L = (kind: Layer["kind"], target: Layer["target"], subgraph: Layer["subgraph"], style?: Layer["style"]) => makeLayer(kind, target, subgraph, "", style ? { style } : {});

const HAND: Layer[] = [
  L("show", "nodes", {}),
  L("hide", "edges", {}),
  L("show", "nodes", { nodes: [{ t: "all" }] }),
  L("show", "nodes", { nodes: [{ t: "type", value: ["paper", "idea"] }, { t: "degree", op: ">=", n: 3 }] }),
  L("hide", "nodes", { nodes: [{ t: "hops", of: "Learning theory", n: 3 }, { t: "hops", of: FAVORITES, n: 2 }, { t: "hops", of: FOCUS, n: 1 }] }),
  L("show", "nodes", { nodes: [{ t: "paths", a: "A", b: "B", n: 4 }] }),
  L("show", "nodes", { nodes: [{ t: "hasEdge", type: "contradicts" }, { t: "hasEdge", type: "supports", exists: false }] }),
  L("show", "nodes", { nodes: [{ t: "linkedFromType", type: "think" }, { t: "createdWithin", days: 30 }, { t: "inArea", area: "Learning theory" }] }),
  L("show", "nodes", { nodes: [{ t: "about", phrase: 'say "hi" \\ there' }, { t: "favorite" }, { t: "mentionedIn", chat: "last week" }, { t: "text", phrase: "gradient" }] }),
  L("show", "nodes", { nodes: [{ t: "name", slugs: ["a-b", "Some Page"] }, { t: "not", cond: { t: "degree", op: "=", n: 0 } }, { t: "not", cond: { t: "not", cond: { t: "favorite" } } }] }),
  L("hide", "edges", { edges: [{ t: "type", value: "mentions" }, { t: "count", op: "<", n: 3 }, { t: "direction", value: "in" }] }),
  L("show", "edges", { edges: [{ t: "endpoints", slugs: ["x", "y"] }] }),
  L("style", "nodes", {}, { color: "type" }),
  L("style", "nodes", {}, { size: { by: "year" } }),
  L("style", "nodes", { nodes: [{ t: "type", value: "paper" }] }, { label: "title" }),
  L("style", "edges", { edges: [{ t: "type", value: "contradicts" }] }, { width: "thick" }),
  L("style", "edges", {}, { width: { by: "count" } }),
];

describe("the query language round trip", () => {
  const fixtures = [...HAND, ...SENTENCES.flatMap((s) => fromSentence(s.text).layers)];

  it("has fixtures to run over", () => expect(fixtures.length).toBeGreaterThan(25));

  it.each(fixtures.map((l, i) => [i, print(l), l] as const))("parse(print(layer)) is the layer: %i %s", (_i, line, layer) => {
    const back = parse(line);
    expect(isParseError(back)).toBe(false);
    expect(noId(back as Layer)).toEqual(noId(layer));
    expect(print(back as Layer)).toBe(line);
  });

  it("writes the lines of the spec", () => {
    expect(print(HAND[3]!)).toBe("show nodes type paper or idea and degree >= 3");
    expect(print(HAND[5]!)).toBe('show nodes paths between "A" and "B" up to 4 hops');
    expect(print(HAND[14]!)).toBe("style nodes label by title for type paper");
    expect(print(HAND[6]!)).toBe("show nodes having edge contradicts and having edge supports exists = false");
  });

  it("keeps a quoted `and` inside its name", () => {
    const l = parse('show nodes name "Rock and roll" and degree > 1') as Layer;
    expect(l.subgraph.nodes).toEqual([{ t: "name", slugs: ["Rock and roll"] }, { t: "degree", op: ">", n: 1 }]);
  });
});

describe("parse errors", () => {
  it.each([
    ["", 0],
    ["hide everything", 0],
    ["show nodes degree about 3", 11],
    ["show nodes type paper and flavour sweet", 11],
    ["style nodes color type", 0],
    ['show nodes about "unterminated', 11],
  ])("%j is refused at %i", (line, at) => {
    const r = parse(line);
    expect(isParseError(r)).toBe(true);
    expect((r as { at: number }).at).toBe(at);
  });
});
