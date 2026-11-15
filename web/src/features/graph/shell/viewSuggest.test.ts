import { withFlag } from "@/flags/testing";
import { fromSentence } from "../layers/sentence";
import { suggestViews } from "./viewSuggest";

const KINDS = ["wikilink", "related"];
const lines = (text: string, kinds: string[] = []) => suggestViews(text, kinds).rows.map((s) => s.line);
const first = (text: string, kinds: string[] = []) => suggestViews(text, kinds).first;

describe("suggestViews", () => {
  it("one shape word offers ready view lines, from its first letters, and goes first", () => {
    expect(lines("orp")).toEqual(["only orphans", "don't show orphans"]);
    expect(first("orp")).toBe(true);
    expect(lines("orphans")).toContain("don't show orphans");
    expect(lines("hubs")).toEqual(["only hubs", "don't show hubs"]);
    expect(lines("leaves")).toEqual(["only leaves", "don't show leaves"]);
    expect(lines("colo")).toEqual(["colour by maturity", "colour by area"]);
  });

  it("edge words name only the link kinds the graph has", () => {
    expect(lines("edg", KINDS)).toEqual(["only wikilink edges", "hide wikilink edges", "only related edges", "hide related edges"]);
    expect(lines("edges", [])).toEqual([]);
    // a kind typed next to an edge word: the line itself reads as a view, then that kind's lines
    expect(lines("related edges", KINDS).slice(0, 3)).toEqual(["related edges", "only related edges", "hide related edges"]);
    // a kind name alone is a search
    expect(lines("related", KINDS)).toEqual([]);
  });

  it("a whole line the rules read as a view change is offered first, as typed", () => {
    const s = suggestViews("papers with more than 5 links");
    expect(s.first).toBe(true);
    expect(s.rows[0]).toMatchObject({ line: "papers with more than 5 links", whole: true });
    expect(s.rows[0]!.hint).toBe("show nodes type paper and degree > 5");
  });

  it("a short search with a shape word at an end offers the lines after the pages, never first", () => {
    expect(lines("node degree")).toContain("pages with more than 5 links");
    expect(first("node degree")).toBe(false);
    expect(first("edge computing", KINDS)).toBe(false);
  });

  it("an ordinary search offers nothing, and nothing first", () => {
    for (const t of ["papers", "learning theory", "lin", "linear algebra", "hubble", "nod", "graph link prediction", "size of the universe", "degree of separation", "hub and spoke", "color theory of art", "node js runtime", "rel", "relativity", "iso", "isolation", "col", "", "> only orphans", "/views"]) {
      expect(lines(t, KINDS), t).toEqual([]);
      expect(first(t, KINDS), t).toBe(false);
    }
  });

  it("every ready line is read by the rules", () => {
    for (const t of ["orp", "hubs", "leaves", "nodes", "edges", "colour", "size"])
      for (const s of suggestViews(t, KINDS).rows) {
        const r = fromSentence(s.line);
        expect(r.unknown, s.line).toBeUndefined();
        expect(r.layers.length, s.line).toBeGreaterThan(0);
      }
  });
});

describe("flag graph-algos: graph-theory words suggest graph-theory lines", () => {
  it("on: a graph-theory word offers its lines after the page results; a line that needs names only fills", () =>
    withFlag("graph-algos", true, () => {
      expect(lines("communities")).toEqual(["colour by community", "largest community"]);
      expect(lines("betweenness")).toEqual(["top 10 by betweenness", "top 10 by pagerank"]);
      expect(lines("bridges")).toEqual(["cut vertices", "bridges"]);
      expect(lines("cliq")).toEqual(["cliques of 4+", "triangles"]);
      // these words are search words too: the page results stay first and keep Enter
      expect(first("communities")).toBe(false);
      expect(first("core")).toBe(false);
      const path = suggestViews("shortest path").rows[0]!;
      expect(path).toMatchObject({ line: "shortest path between ", fill: true });
      expect(suggestViews("neighbours").rows[0]).toMatchObject({ line: "near ", fill: true });
      // a whole line the rules read as a graph-theory view goes first
      expect(suggestViews("top 10 by betweenness").rows[0]).toMatchObject({ whole: true, line: "top 10 by betweenness" });
      expect(first("top 10 by betweenness")).toBe(true);
    }));

  it("on: every line it suggests reads as a view (a line that needs names is filled in first)", () =>
    withFlag("graph-algos", true, () => {
      const words = ["communities", "betweenness", "bridges", "cliques", "core", "components"];
      const offered = words.flatMap((w) => suggestViews(w).rows.filter((r) => !r.fill).map((r) => r.line));
      expect(offered.length).toBeGreaterThanOrEqual(10);
      for (const l of offered) expect(fromSentence(l).unknown, l).toBeUndefined();
      expect(fromSentence('shortest path between "A" and "B"').unknown).toBeUndefined();
      expect(fromSentence('near "A"').unknown).toBeUndefined();
      // a quoted page name is not a graph-theory word: no whole-line view for a title with "community" in it
      expect(suggestViews('papers about "community detection"').rows.some((r) => r.whole)).toBe(false);
    }));

  it("off: no graph-theory lines", () =>
    withFlag("graph-algos", false, () => {
      expect(lines("communities")).toEqual([]);
      expect(lines("shortest path")).toEqual([]);
      expect(first("top 10 by betweenness")).toBe(false);
    }));
});
