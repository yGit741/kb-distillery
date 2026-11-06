import { clearMeaningCache, needsMeaning, resolveAbout, SIMILAR_K } from "./meaning";
import { EMPTY_STACK, evaluate, makeLayer, stack } from "./model";
import { sampleLinks, sampleNodes } from "../fixtures";

const about = (phrase: string, extra: object = {}) => makeLayer("show", "nodes", { nodes: [{ t: "about", phrase, ...extra }] }, `about "${phrase}"`);

beforeEach(() => clearMeaningCache());

describe("resolveAbout", () => {
  it("keeps the phrase, adds the top pages, and asks once per phrase", async () => {
    const similar = vi.fn(async () => ["idea-margin", "jane-doe"]);
    const layers = [about("Overfitting"), about("overfitting")];
    expect(needsMeaning(layers)).toBe(true);
    const r = await resolveAbout(layers, similar);
    expect(r).toMatchObject({ ok: true });
    if (!r.ok) return;
    expect(r.layers.map((l) => l.subgraph.nodes)).toEqual([[{ t: "about", phrase: "Overfitting", slugs: ["idea-margin", "jane-doe"] }], [{ t: "about", phrase: "overfitting", slugs: ["idea-margin", "jane-doe"] }]]);
    expect(similar).toHaveBeenCalledTimes(1);
    expect(similar).toHaveBeenCalledWith({ q: "Overfitting", k: SIMILAR_K });
    expect(needsMeaning(r.layers)).toBe(false);
  });

  it("reaches inside not, and a page asks with its own card", async () => {
    const similar = vi.fn(async () => ["a"]);
    const l = makeLayer("hide", "nodes", { nodes: [{ t: "not", cond: { t: "about", phrase: "x", slug: "idea-margin" } }] });
    const r = await resolveAbout([l], similar);
    expect(similar).toHaveBeenCalledWith({ slug: "idea-margin", k: SIMILAR_K });
    expect(r.ok && r.layers[0]!.subgraph.nodes).toEqual([{ t: "not", cond: { t: "about", phrase: "x", slug: "idea-margin", slugs: ["a"] } }]);
  });

  it("$focus needs exactly one focused page, and uses it as the slug", async () => {
    const similar = vi.fn(async () => ["a"]);
    expect(await resolveAbout([about("$focus")], similar)).toEqual({ ok: false, reason: "focus" });
    expect(similar).not.toHaveBeenCalled();
    await resolveAbout([about("$focus")], similar, "kernel");
    expect(similar).toHaveBeenCalledWith({ slug: "kernel", k: SIMILAR_K });
  });

  it("leaves an about unanswered, never throwing, when the service is off or fails", async () => {
    const layers = [about("x")];
    expect(await resolveAbout(layers, null)).toEqual({ ok: true, layers });
    const r = await resolveAbout(layers, async () => {
      throw new Error("503");
    });
    expect(r).toEqual({ ok: true, layers });
    // a failure is not remembered
    const again = await resolveAbout(layers, async () => ["z"]);
    expect(again.ok && again.layers[0]!.subgraph.nodes).toEqual([{ t: "about", phrase: "x", slugs: ["z"] }]);
  });
});

describe("evaluate with about", () => {
  const g = { nodes: sampleNodes, links: sampleLinks };
  it("keeps the named pages, and names the reason when it was never answered", () => {
    const done = evaluate(stack(EMPTY_STACK, [about("x", { slugs: ["idea-margin", "gone"] })]), g);
    expect([...done.nodeIds!]).toEqual(["idea-margin"]);
    expect(done.skipped).toEqual([]);
    const open = evaluate(stack(EMPTY_STACK, [about("x")]), g);
    expect(open.skipped.join("|")).toMatch(/about "x" \(meaning search is off\)/);
  });
});
