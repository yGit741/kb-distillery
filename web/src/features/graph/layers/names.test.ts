import { node } from "../fixtures";
import { FAVORITES, FOCUS, makeLayer } from "./model";
import { resolveName, resolveNames } from "./names";

const nodes = [
  node("learning-theory", { title: "Learning theory", inDegree: 5 }),
  node("learning-curves", { title: "Learning curves", inDegree: 2 }),
  node("compression", { title: "Compression" }),
  node("compression-ratio", { title: "Compression ratio" }),
  node("margin", { title: "Margin", properties: { aliases: "slack, gap" } }),
  node("generalization-bound", { title: "Generalization bound" }),
  node("copy-a", { title: "Twin" }),
  node("copy-b", { title: "Twin" }),
];
const show = (...conds: Parameters<typeof makeLayer>[2]["nodes"] & object[]) => makeLayer("show", "nodes", { nodes: conds });

describe("resolveName", () => {
  it("takes an exact title, ignoring case", () => expect(resolveName("learning THEORY", nodes)).toEqual({ slug: "learning-theory" }));
  it("takes a slug and an alias", () => {
    expect(resolveName("learning-curves", nodes)).toEqual({ slug: "learning-curves" });
    expect(resolveName("slack", nodes)).toEqual({ slug: "margin" });
  });
  it("exact beats a longer title that starts the same", () => expect(resolveName("Compression", nodes)).toEqual({ slug: "compression" }));
  it("takes a unique prefix", () => expect(resolveName("Generaliz", nodes)).toEqual({ slug: "generalization-bound" }));
  it("is ambiguous on a shared prefix, most linked first", () => {
    const r = resolveName("Learning", nodes);
    expect(r).toEqual({ name: "Learning", options: [{ slug: "learning-theory", title: "Learning theory" }, { slug: "learning-curves", title: "Learning curves" }] });
  });
  it("is ambiguous on two exact titles", () => expect("options" in resolveName("Twin", nodes) && (resolveName("Twin", nodes) as { options: unknown[] }).options).toHaveLength(2));
  it("reports an unknown name with no options", () => expect(resolveName("Zebra crossing", nodes)).toEqual({ name: "Zebra crossing", options: [] }));
  it("offers near matches for a name inside a title", () => {
    const r = resolveName("ratio", nodes) as { options: { slug: string }[] };
    expect(r.options.map((o) => o.slug)).toEqual(["compression-ratio"]);
  });
});

describe("resolveNames", () => {
  it("maps every name in every layer and leaves the words alone", () => {
    const layers = [show({ t: "hops", of: "Learning theory", n: 2 }, { t: "hops", of: FAVORITES, n: 1 }), show({ t: "paths", a: "Margin", b: "Compression", n: 4 }, { t: "name", slugs: ["Generaliz"] })];
    const r = resolveNames(layers, nodes);
    expect(r.ambiguous).toEqual([]);
    expect(r.layers[0]!.subgraph.nodes).toEqual([{ t: "hops", of: "learning-theory", n: 2 }, { t: "hops", of: FAVORITES, n: 1 }]);
    expect(r.layers[1]!.subgraph.nodes).toEqual([{ t: "paths", a: "margin", b: "compression", n: 4 }, { t: "name", slugs: ["generalization-bound"] }]);
    expect(layers[0]!.subgraph.nodes![0]).toEqual({ t: "hops", of: "Learning theory", n: 2 });
  });

  it("collects each ambiguous or unknown name once", () => {
    const r = resolveNames([show({ t: "hops", of: "Learning", n: 1 }, { t: "hops", of: "Learning", n: 2 }, { t: "hops", of: "Nope", n: 1 })], nodes);
    expect(r.ambiguous.map((a) => [a.name, a.options.length])).toEqual([["Learning", 2], ["Nope", 0]]);
  });

  it("uses a name the user picked, and fills the focus", () => {
    const r = resolveNames([show({ t: "hops", of: "Learning", n: 1 }, { t: "hops", of: FOCUS, n: 1 })], nodes, { chosen: { Learning: "learning-curves" }, focus: "margin" });
    expect(r.ambiguous).toEqual([]);
    expect(r.layers[0]!.subgraph.nodes).toEqual([{ t: "hops", of: "learning-curves", n: 1 }, { t: "hops", of: "margin", n: 1 }]);
  });
});
