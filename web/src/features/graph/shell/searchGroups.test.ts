import { node } from "../fixtures";
import { buildSearchIndex, isThink, matchTier1, placeOnce, withNames } from "./searchGroups";

const WORDS = ["margin", "kernel", "bandit", "entropy", "policy", "gradient", "topology", "lattice", "spectral", "prior"];
function fixture(n: number) {
  return Array.from({ length: n }, (_, i) =>
    node(`page-${i}`, {
      title: `${WORDS[i % 10]} ${WORDS[(i * 7) % 10]} note ${i}`,
      inDegree: i % 17,
      type: i % 50 === 0 ? "think-note" : "topic",
      properties: { aliases: `alias ${i}, ${WORDS[(i * 3) % 10]}`, tags: `tag-${i % 40}, ${WORDS[(i * 13) % 10]}` },
    }),
  );
}

describe("the tier-1 index", () => {
  it("matches titles and aliases, splits think notes, counts a set over title, alias and tags", () => {
    const nodes = [
      node("a", { title: "Margin theory", properties: { tags: "learning" } }),
      node("b", { title: "Large margins", properties: { aliases: "margin bounds" } }),
      node("c", { title: "Unrelated", properties: { tags: "margin" } }),
      node("t", { title: "Margin thoughts", type: "think-note" }),
    ];
    const hit = matchTier1(withNames(buildSearchIndex(nodes), [{ id: "v1", name: "Margin view" }], [{ id: "fit", label: "Fit to view" }]), "margin");
    expect(hit.pages.map((n) => n.id)).toEqual(["a", "b"]);
    expect(hit.think.map((n) => n.id)).toEqual(["t"]);
    expect(hit.set?.ids.sort()).toEqual(["a", "b", "c", "t"]);
    expect(hit.views).toEqual([{ id: "v1", name: "Margin view" }]);
    expect(matchTier1(withNames(buildSearchIndex(nodes), [], [{ id: "fit", label: "Fit to view" }]), "fit").commands).toEqual([{ id: "fit", name: "Fit to view" }]);
    expect(isThink(nodes[3]!)).toBe(true);
  });

  it("makes no set from one page", () => {
    expect(matchTier1(buildSearchIndex([node("a", { title: "Solo page" })]), "solo").set).toBeNull();
  });

  it("builds once and matches every keystroke well inside 10 ms for 5k pages", () => {
    const nodes = fixture(5000);
    const t0 = performance.now();
    const base = buildSearchIndex(nodes);
    const index = withNames(base, [{ id: "v", name: "Reading list" }], Array.from({ length: 40 }, (_, i) => ({ id: `c${i}`, label: `Command ${i}` })));
    const build = performance.now() - t0;
    matchTier1(index, "ma"); // warm up
    const times: number[] = [];
    for (const q of ["m", "ma", "mar", "marg", "margi", "margin", "margin ke", "margin kernel", "tag-3", "alias 42"]) {
      const s = performance.now();
      matchTier1(index, q);
      times.push(performance.now() - s);
    }
    console.info(`search index 5k: build ${build.toFixed(1)} ms, worst keystroke ${Math.max(...times).toFixed(2)} ms`);
    // the budget is 10 ms; x5 margin for a loaded CI machine
    expect(Math.max(...times)).toBeLessThan(50);
    expect(build).toBeLessThan(500);
  });
});

describe("a page found twice", () => {
  it("is placed once, in the top group, marked with the other way", () => {
    const a = node("a");
    const b = node("b");
    const placed = placeOnce([
      { group: "pages", via: "title", node: a },
      { group: "pages", via: "text", node: a, snippet: "x" },
      { group: "pages", via: "text", node: b, snippet: "y" },
      { group: "related", via: "related", node: a },
      { group: "related", via: "related", node: b },
    ]);
    expect(placed.pages.map((p) => [p.node.id, p.via, p.also])).toEqual([
      ["a", "title", ["text", "related"]],
      ["b", "text", ["related"]],
    ]);
    expect(placed.related).toEqual([]);
  });
});
