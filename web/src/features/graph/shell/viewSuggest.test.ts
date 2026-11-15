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
