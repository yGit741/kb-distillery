import { withFlag } from "@/flags/testing";
import { node } from "../fixtures";
import { completeName, namePages, nameSlot, putName } from "./nameComplete";
import { readableLine, resolveName, resolveNames, uniqueTitles } from "./names";
import { makeLayer } from "./model";
import { fromSentence } from "./sentence";

const nodes = [
  node("learning-theory", { title: "Learning theory", inDegree: 5 }),
  node("learning-rate", { title: "Learning rate", inDegree: 1 }),
  node("juntas", { title: "Juntas" }),
  node("signal-noise", { title: "Signal and noise" }),
  node("bias-a", { title: "Bias" }),
  node("bias-b", { title: "Bias" }),
  node("orphans-page", { title: "Orphans" }),
  node("theory-of-mind", { title: "Theory of mind" }),
];
const unique = uniqueTitles(nodes);
const partial = (line: string) => nameSlot(line)?.partial ?? null;

describe("page names inside a > line: where one is being typed", () => {
  it("after a word that takes a page", () => {
    expect(partial("> near learning th")).toBe("learning th");
    expect(partial("> within 2 hops of jun")).toBe("jun");
    expect(partial("> community of Lea")).toBe("Lea");
    expect(partial("> similar to jun")).toBe("jun");
    expect(partial("> close to jun")).toBe("jun");
    expect(partial('> near "Learn')).toBe("Learn");
  });

  it("the second name of a pair, after and / to", () => {
    expect(partial('> shortest path between "Learning theory" and ju')).toBe("ju");
    expect(partial("> shortest path from juntas to lea")).toBe("lea");
    expect(partial("> common neighbours of Juntas and Bi")).toBe("Bi");
  });

  it("a trigger word inside an open quoted name is part of the name", () => {
    expect(partial('> between "Signal and no')).toBe("Signal and no");
  });

  it("no name: a closed quote, a number, a view word, a new clause, too short", () => {
    // completeName: no pages offered (the fixture has a page called "Orphans", so a slot would show)
    const offered = (line: string) => completeName(line, nodes)?.slot.partial ?? null;
    expect(offered('> near "Learning theory" ')).toBeNull();
    expect(offered("> cliques of 4")).toBeNull();
    expect(offered("> cliques of 4+")).toBeNull();
    expect(offered("> hide people and orph")).toBeNull();
    expect(offered("> papers with more than 5 links")).toBeNull();
    expect(offered("> near this")).toBeNull();
    expect(offered("> near learning theory, colour by theme")).toBeNull();
    expect(offered("> near l")).toBeNull();
    expect(offered("> top 10 by betweenness")).toBeNull();
    expect(offered("> shortest path between Juntas and their neighbours")).toBeNull();
    // a later clause's "and" is not the pair's second name
    expect(offered('> between "a" and "b", hide people and orphans')).toBeNull();
    expect(offered("> paths from a to b then hide people and orph")).toBeNull();
  });

  it("a title that holds a trigger word is read whole when it names a page", () => {
    expect(completeName("> near theory of mi", nodes)?.slot.partial).toBe("theory of mi");
    expect(completeName("> near theory of mi", nodes)?.pages[0]?.id).toBe("theory-of-mind");
    // a pair's second name is read from its own trigger
    expect(completeName("> shortest path between Learning theory and ju", nodes)?.slot.partial).toBe("ju");
    expect(completeName("> near zzz", nodes)).toBeNull();
  });
});

describe("page names inside a > line: which pages, and putting one in", () => {
  it("the search's own matches, then titles within a small typo", () => {
    expect(namePages(nodes, "learning th")[0]?.id).toBe("learning-theory");
    expect(namePages(nodes, "lerning th")[0]?.id).toBe("learning-theory");
    expect(namePages(nodes, "lerning th").map((n) => n.id)).not.toContain("learning-rate");
    expect(namePages(nodes, "jun").map((n) => n.id)).toEqual(["juntas"]);
    expect(namePages(nodes, "zzz")).toEqual([]);
  });

  it("puts the quoted title in, or the slug when the title is not the page's alone", () => {
    const line = "> near learning th";
    expect(putName(line, nameSlot(line)!, nodes[0]!, unique)).toBe('> near "Learning theory" ');
    const quoted = '> between "Signal and no';
    expect(putName(quoted, nameSlot(quoted)!, nodes[3]!, unique)).toBe('> between "Signal and noise" ');
    const dup = "> near bia";
    expect(putName(dup, nameSlot(dup)!, nodes[4]!, unique)).toBe('> near "bias-a" ');
  });
});

describe("resolved lines read with titles", () => {
  it("a title named by one page only; a written line's slug resolves first, a typed name still asks", () => {
    expect(unique.has("learning theory")).toBe(true);
    expect(unique.has("bias")).toBe(false);
    // a title another page has as its slug is not unique either
    const clash = [node("a", { title: "juntas" }), node("juntas", { title: "Something" })];
    expect(uniqueTitles(clash).has("juntas")).toBe(false);
    expect(resolveName("juntas", clash)).toMatchObject({ name: "juntas" });
    const written = [makeLayer("show", "nodes", { nodes: [{ t: "hops", of: "juntas", n: 1 }] })];
    expect(resolveNames(written, clash, { slugFirst: true }).layers[0]!.subgraph.nodes).toEqual([{ t: "hops", of: "juntas", n: 1 }]);
    expect(resolveNames(written, clash).ambiguous).toHaveLength(1);
  });

  it("slugs become titles where the title reads back to the same page", () => {
    const byId = new Map(nodes.map((n) => [n.id, n] as const));
    expect(readableLine('show nodes shortest path between "learning-theory" and "bias-b"', byId, unique)).toBe('show nodes shortest path between "Learning theory" and "bias-b"');
    expect(readableLine('show nodes about "learning"', byId, unique)).toBe('show nodes about "learning"');
    expect(resolveName("Learning theory", nodes)).toEqual({ slug: "learning-theory" });
  });
});

describe("flag graph-algos: quoted names and near", () => {
  it("on: a quoted title with 'and' or a comma stays one name", () =>
    withFlag("graph-algos", true, () => {
      expect(fromSentence('shortest path between "Signal and noise" and "Juntas"').lines).toEqual(['show nodes shortest path between "Signal and noise" and "Juntas"']);
      expect(fromSentence('common neighbours of "Signal and noise" and Juntas').lines).toEqual(['show nodes common neighbours of "Signal and noise" and "Juntas"']);
      expect(fromSentence('near "Bias, variance", colour by theme').lines).toEqual(['show nodes within 1 hop of "Bias, variance"', "style nodes color by area"]);
    }));

  it("on: near, close to and around read as one hop", () =>
    withFlag("graph-algos", true, () => {
      expect(fromSentence("near Learning theory").lines).toEqual(['show nodes within 1 hop of "Learning theory"']);
      expect(fromSentence("pages close to Juntas").lines).toEqual(['show nodes within 1 hop of "Juntas"']);
      expect(fromSentence("everything around this").layers[0]?.subgraph.nodes).toEqual([{ t: "hops", of: "$focus", n: 1 }]);
    }));

  it("off: near is not read by the rules (the model reads it); quotes and typo mending read as before", () =>
    withFlag("graph-algos", false, () => {
      expect(fromSentence("near Learning theory").unknown).toBe("near Learning theory");
      // a comma inside quotes still splits the line; a typo after "from" is still mended
      expect(fromSentence('text "a, b"').lines).not.toEqual(['show nodes text "a, b"']);
      expect(fromSentence("only papers from 2020 colur by theme").lines).toEqual(fromSentence("only papers from 2020 colour by theme").lines);
    }));

  it("on: an unbalanced quote does not swallow the next clause", () =>
    withFlag("graph-algos", true, () => {
      const lines = fromSentence('only papers, hide "people').lines;
      expect(lines[0]).toBe("show nodes type paper");
      expect(lines).toHaveLength(2);
    }));
});
