import { SAMPLE_ITEM as item } from "./fixtures";
import { fitTitle } from "./TouchedGraph";
import { NO_DECISIONS, acceptAdditions, acceptBulk, acceptRestOfPage, applyCount, bulkLabel, groupsOf, lookPages, openOf, openOnPage, pageSummary } from "./model";

const page = (slug: string) => item.pages.find((p) => p.slug === slug)!;

describe("edit preview model", () => {
  it("sends rewrites and everything on a protected page to Needs a look", () => {
    const g = groupsOf(item);
    expect(g.look.map((r) => r.change.id)).toEqual(["a1", "a2", "s1"]);
    expect(g.lookBulk.map((p) => p.slug)).toEqual(["attention"]);
    expect(g.additions.map((r) => r.change.id)).toEqual(["n1", "n2", "k1"]);
    expect(g.bulk.map((p) => p.slug)).toEqual(["sparse-attention", "flashattention"]);
  });

  it("counts what is open, links and fixes one by one", () => {
    expect(openOf(item, NO_DECISIONS)).toEqual({ look: 4, additions: 3, bulk: 6, total: 13 });
  });

  it("bulk accepts never touch a rewrite or a protected page", () => {
    const d = acceptBulk(item, acceptAdditions(item, NO_DECISIONS));
    expect(d.changes).toEqual({ n1: "accepted", n2: "accepted", k1: "accepted" });
    expect(d.bulk).toEqual({ "sparse-attention": "accepted", flashattention: "accepted" });
    expect(openOf(item, d)).toEqual({ look: 4, additions: 0, bulk: 0, total: 4 });
    expect(acceptRestOfPage(page("attention"), NO_DECISIONS)).toBe(NO_DECISIONS);
  });

  it("accepting the rest of a page keeps what was already rejected", () => {
    const d = acceptRestOfPage(page("sparse-attention"), { ...NO_DECISIONS, changes: { n1: "rejected" } });
    expect(d.changes).toEqual({ n1: "rejected", n2: "accepted" });
    expect(d.bulk).toEqual({ "sparse-attention": "accepted" });
    expect(openOnPage(page("sparse-attention"), d)).toBe(0);
  });

  it("apply counts only what was accepted", () => {
    const d = { ...NO_DECISIONS, changes: { a1: "accepted", s1: "rejected" } as const, bulk: { flashattention: "accepted" } as const };
    expect(applyCount(item, d)).toEqual({ changes: 5, pages: 2 });
  });

  it("steps the page view through the pages that need a look, and words the counts", () => {
    expect(lookPages(item).map((p) => p.slug)).toEqual(["attention", "scaling-laws"]);
    expect(pageSummary(page("attention"))).toBe("1 rewrite, 1 addition, 1 link");
    expect(bulkLabel(page("flashattention"))).toBe("3 links, 1 fix");
    expect(bulkLabel({ links: 0, fixes: 2 })).toBe("2 fixes");
  });

  it("graph labels keep whole words", () => {
    expect(fitTitle("KV cache", 16)).toBe("KV cache");
    expect(fitTitle("Senior ML Engineer, Perception (Acme)", 16)).toBe("Senior ML …");
    expect(fitTitle("Negation-aware-clinical-ner", 16)).toBe("Negation-aware-c …");
  });
});
