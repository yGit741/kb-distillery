import { node, sampleNodes } from "./fixtures";
import { buildNeighborMap } from "./graphData";
import { extendView, findPages, makeView, parsePages, scopeIds, scorePage, textHits } from "./pageSearch";

describe("scorePage / findPages", () => {
  const n = node("2019-fine-grained", { title: "Fine-Grained Analysis of Margin" });
  it("ranks exact, prefix, word, substring, slug and multi-term matches", () => {
    expect(scorePage(node("x", { title: "margin" }), "margin")).toBe(100);
    expect(scorePage(n, "fine-grained")).toBe(80);
    expect(scorePage(n, "ned analysis")).toBe(50);
    expect(scorePage(n, "analysis")).toBe(62);
    expect(scorePage(node("big-nets", { title: "Why" }), "big nets")).toBe(40);
    expect(scorePage(node("zz", { title: "alpha beta" }), "beta zz")).toBe(30);
    expect(scorePage(n, "nothing")).toBe(0);
    expect(scorePage(n, "")).toBe(0);
  });
  it("orders matches best first and limits", () => {
    const r = findPages(sampleNodes, "learning");
    expect(r[0]?.id).toBe("topic-learning-theory");
    expect(findPages(sampleNodes, "   ")).toEqual([]);
    expect(findPages(sampleNodes, "a", 2).length).toBeLessThanOrEqual(2);
  });
});

describe("textHits", () => {
  const byId = new Map(sampleNodes.map((m) => [m.id, m] as const));
  it("drops title matches already listed and pages that are not in the graph", () => {
    const hits = [
      { id: "idea-margin", title: "", type: "idea", score: 1, snippet: "s" },
      { id: "q-why-big-nets-work", title: "", type: "question", score: 1, snippet: "s" },
      { id: "ghost", title: "", type: "idea", score: 1, snippet: "s" },
    ];
    expect(textHits(hits, byId, [byId.get("idea-margin") as never]).map((h) => h.id)).toEqual(["q-why-big-nets-work"]);
  });
});

describe("views", () => {
  const byId = new Map(sampleNodes.map((m) => [m.id, m] as const));
  const nb = buildNeighborMap([{ source: "idea-margin", target: "2019-fine-grained" }]);
  it("makes a view of the known pages plus neighbours, or null", () => {
    const v = makeView("picked", "picked", ["idea-margin", "ghost"], byId, nb);
    expect([...(v?.hits ?? [])]).toEqual(["idea-margin"]);
    expect([...(v?.shown ?? [])].sort()).toEqual(["2019-fine-grained", "idea-margin"]);
    expect(makeView("search", "q", ["ghost"], byId, nb)).toBeNull();
  });
  it("picking more extends a picked view; other views are replaced", () => {
    const a = makeView("picked", "picked", ["idea-margin"], byId, nb);
    const b = makeView("picked", "picked", ["jane-doe"], byId, nb);
    expect([...(extendView(a, b)?.hits ?? [])].sort()).toEqual(["idea-margin", "jane-doe"]);
    const s = makeView("search", "q", ["jane-doe"], byId, nb);
    expect(extendView(a, s)).toBe(s);
    expect(extendView(a, null)).toBeNull();
  });
  it("parses ?pages= and scope projections", () => {
    expect(parsePages("a, b,,c ")).toEqual(["a", "b", "c"]);
    expect(parsePages(undefined)).toEqual([]);
    expect(scopeIds("scope-x", { hop0: ["a", 3], hop1: ["b"] })).toEqual(["scope-x", "a", "b"]);
    expect(scopeIds("scope-x", undefined)).toEqual(["scope-x"]);
  });
});
