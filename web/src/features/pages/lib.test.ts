import type { PageCard, PageIndex } from "@/api/types";
import {
  buildGraph, filterCards, highlightParts, homeSections, layerOf, parseLegacyHash, prepareMarkdown, resolveInput,
  ringLayout, sortCards, suggest, withPinToggled, withTrail, TRAIL_MAX,
} from "./lib";

const card = (id: string, o: Partial<PageCard> = {}): PageCard => ({
  id, title: id.toUpperCase(), type: "paper", maturity: "", depth: "", areas: [], preview: "", words: 100, ...o,
});
const index: PageIndex = {
  generated_at: "t",
  pages: [
    card("a", { depth: "deep", words: 900, year: 2020 }),
    card("b", { type: "topic", title: "Tensor rank" }),
    card("c", { type: "question", maturity: "open" }),
    card("d", { type: "person" }),
    card("e", { depth: "listed", words: 50, year: 2024 }),
  ],
  links: [["a", "b"], ["b", "a"], ["c", "a"], ["d", "a"], ["e", "a"], ["a", "c"]],
  wanted: [],
  wanted_total: 0,
};
const g = buildGraph(index);

describe("model + graph", () => {
  it("maps types to layers", () => {
    expect(layerOf("paper")).toBe("source");
    expect(layerOf("course")).toBe("collection");
    expect(layerOf("person")).toBe("concept");
    expect(layerOf("nope")).toBeUndefined();
  });
  it("builds directed adjacency", () => {
    expect([...g.out.get("a")!].sort()).toEqual(["b", "c"]);
    expect([...g.inn.get("a")!].sort()).toEqual(["b", "c", "d", "e"]);
  });
  it("sorts and filters cards", () => {
    const all = [...g.byId.values()];
    expect(filterCards(all, { type: "paper" }).map((c) => c.id)).toEqual(["a", "e"]);
    expect(filterCards(all, { layer: "concept" })).toHaveLength(3);
    expect(sortCards(g, all, "year")[0]!.id).toBe("e");
    expect(sortCards(g, all, "links")[0]!.id).toBe("a");
  });
  it("derives the home sections", () => {
    const h = homeSections(g);
    expect(h.deep.map((c) => c.id)).toEqual(["a"]);
    expect(h.questions.map((c) => c.id)).toEqual(["c"]);
    expect(h.counts.get("paper")).toBe(2);
    expect(h.orphans.map((c) => c.id)).toContain("d");
  });
});

describe("legacy links", () => {
  it("parses the old hash routes", () => {
    expect(parseLegacyHash("#/p/some-slug")).toEqual({ kind: "page", slug: "some-slug" });
    expect(parseLegacyHash("#/p/a%20b")).toEqual({ kind: "page", slug: "a b" });
    expect(parseLegacyHash("#/search/tensor%20rank")).toEqual({ kind: "search", q: "tensor rank" });
    expect(parseLegacyHash("#/browse/paper/year")).toEqual({ kind: "browse", type: "paper" });
    expect(parseLegacyHash("#/path/x/y")).toEqual({ kind: "path", a: "x", b: "y" });
    expect(parseLegacyHash("#/")).toBeNull();
    expect(parseLegacyHash("")).toBeNull();
  });
});

describe("trail and pins", () => {
  it("moves a revisited page to the front and caps the trail", () => {
    expect(withTrail(["x", "y"], "y")).toEqual(["y", "x"]);
    const long = Array.from({ length: 30 }, (_, i) => `s${i}`);
    expect(withTrail(long, "new")).toHaveLength(TRAIL_MAX);
  });
  it("toggles a pin", () => {
    expect(withPinToggled(["x"], "y")).toEqual(["y", "x"]);
    expect(withPinToggled(["y", "x"], "y")).toEqual(["x"]);
  });
});

describe("markdown prep", () => {
  it("drops comments and the H1, rewrites image embeds and viz blocks", () => {
    const out = prepareMarkdown('# Title\n<!-- hide -->\nbody ![[fig 1.png]]\n```dataviewjs\nconst path = "meta/chats/assets/v.html";\n```');
    expect(out).not.toContain("hide");
    expect(out).not.toMatch(/^# Title/);
    expect(out).toContain("![fig 1.png](/api/assets/vault?name=fig%201.png)");
    expect(out).toContain("/api/assets/chat?path=meta%2Fchats%2Fassets%2Fv.html");
  });
});

describe("wikilink titles", () => {
  it("labels bare wikilinks with the page title and leaves explicit labels and unknown slugs", () => {
    const t = (s: string) => (s === "a" ? "Alpha [x]" : undefined);
    expect(prepareMarkdown("[[a]] [[a|mine]] [[zzz]] [[a#h]]", t)).toBe("[[a|Alpha  x ]] [[a|mine]] [[zzz]] [[a|Alpha  x ]]");
  });
});

describe("search helpers", () => {
  it("suggests by title and slug", () => {
    expect(suggest(g, "tensor")[0]!.id).toBe("b");
    expect(suggest(g, "")).toEqual([]);
  });
  it("resolves a typed title to its slug", () => {
    expect(resolveInput(g, "tensor rank")).toBe("b");
    expect(resolveInput(g, "a")).toBe("a");
    expect(resolveInput(g, "zzz")).toBe("zzz");
  });
  it("splits text around matches without html", () => {
    expect(highlightParts("Tensor ranks (low-rank)", "rank")).toEqual([
      { text: "Tensor ", hit: false }, { text: "rank", hit: true }, { text: "s (low-", hit: false },
      { text: "rank", hit: true }, { text: ")", hit: false },
    ]);
  });
});

describe("ring layout", () => {
  it("marks link direction and counts the cap", () => {
    const r = ringLayout(g, "a", 3);
    expect(r.total).toBe(4);
    expect(r.nodes).toHaveLength(3);
    expect(r.nodes.find((n) => n.id === "b")?.dir).toBe("both");
    expect(r.nodes.find((n) => n.id === "d")?.dir ?? "in").toBe("in");
  });
});
