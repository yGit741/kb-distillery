import { node } from "../fixtures";
import type { GNode } from "../types";
import { DEFAULT_LAB, type LabConfig } from "./config";
import type { Importance } from "./importance";
import { FORCED, labelPx, labelText, planLabels, type PlanInput, type ScreenItem } from "./labelPlan";

const measure = (text: string, px: number) => text.length * px * 0.55;

function grid(n: number, gap: number): { items: ScreenItem[]; imp: Importance } {
  const items: ScreenItem[] = [];
  const score = new Map<string, number>();
  for (let i = 0; i < n; i++) {
    const id = `idea-${String(i).padStart(3, "0")}`;
    items.push({ n: node(id, { type: "idea", title: `Idea ${i}` }), sx: 40 + (i % 20) * gap, sy: 40 + Math.floor(i / 20) * gap, r: 4 });
    score.set(id, 1 - i / n);
  }
  const qrank = new Map([...score.keys()].map((id, i) => [id, i / n]));
  return { items, imp: { score, terms: new Map(), qrank, maxScore: 1 } };
}

function input(o: Partial<Omit<PlanInput, "cfg">> & { cfg?: Partial<LabConfig> }): PlanInput {
  const g = grid(100, 60);
  return {
    items: g.items,
    width: 1200,
    height: 800,
    zr: 1,
    imp: g.imp,
    forced: new Map(),
    hops: null,
    prev: new Map(),
    obstacles: [],
    suppress: false,
    measure,
    ...o,
    cfg: { ...DEFAULT_LAB, ...o.cfg },
  };
}

describe("planLabels", () => {
  it("fills labels in score order until the coverage budget", () => {
    const p = planLabels(input({ cfg: { coverage: 3 } }));
    expect(p.placed.length).toBeGreaterThan(5);
    expect(p.placed.length).toBeLessThan(100);
    expect(p.placed[0]?.id).toBe("idea-000");
    expect(p.coverage).toBeLessThan(4);
  });
  it("never lets two labels overlap", () => {
    const p = planLabels(input({ items: grid(100, 14).items, cfg: { strategy: "all" } }));
    for (const a of p.placed)
      for (const b of p.placed)
        if (a !== b) expect(a.box[0] < b.box[2] && a.box[2] > b.box[0] && a.box[1] < b.box[3] && a.box[3] > b.box[1]).toBe(false);
    expect(p.dropped).toBeGreaterThan(0);
  });
  it("forced labels come first and are kept outside the budget", () => {
    const forced = new Map([["idea-099", FORCED.hover]]);
    const p = planLabels(input({ forced, cfg: { strategy: "count", count: 1 } }));
    expect(p.placed.map((x) => x.id)).toEqual(["idea-099", "idea-000"]);
    expect(p.placed[0]?.text).toBe("Idea 99");
  });
  it("whole-graph choice ignores the viewport, screen choice does not", () => {
    const g = grid(100, 60);
    const shifted = g.items.map((it) => ({ ...it, sx: it.sx + 2000 })); // all off screen
    const world = planLabels(input({ items: shifted, imp: g.imp, cfg: { strategy: "count", count: 10 } }));
    const screen = planLabels(input({ items: shifted, imp: g.imp, cfg: { strategy: "count", count: 10, scope: "screen" } }));
    expect(world.placed.length).toBe(10);
    expect(screen.placed.length).toBe(0);
  });
  it("tries above first and keeps a shown label's previous offset", () => {
    const one = input({ items: grid(1, 60).items, imp: grid(1, 60).imp, cfg: { strategy: "all" } });
    expect(planLabels(one).placed[0]?.pos).toBe(0); // above
    const kept = planLabels({ ...one, prev: new Map([["idea-000", { shown: true, pos: 2 }]]) });
    expect(kept.placed[0]?.pos).toBe(2);
  });
  it("the focus keeps only pages within the hops", () => {
    const hops = new Map([["idea-050", 0], ["idea-051", 1]]);
    const p = planLabels(input({ hops, cfg: { strategy: "all", doiHops: 1 } }));
    expect(p.placed.map((x) => x.id).sort()).toEqual(["idea-050", "idea-051"]);
  });
  it("regions zoomed out leave page labels to hover and selection", () => {
    const p = planLabels(input({ suppress: true, forced: new Map([["idea-005", FORCED.selected]]) }));
    expect(p.placed.map((x) => x.id)).toEqual(["idea-005"]);
  });
});

describe("label text and size", () => {
  const q = node("q-x", { type: "question", title: "Does the low-rank bias of depth need gradient flow?" });
  it("shortens a question to its subject with a ? marker", () => {
    expect(labelText(q, "short", 28)).toBe("? Low-rank bias of depth need…");
    expect(labelText(node("q-y", { type: "question", title: "Can AI-assisted proofs help?" }), "short", 28)).toBe("? AI-assisted proofs help");
  });
  it("drops subtitles and cuts at a word", () => {
    const n = node("p", { type: "paper", title: "Deep learning generalizes: a study of the implicit bias of gradient descent" });
    expect(labelText(n, "short", 28)).toBe("Deep learning generalizes");
    expect(labelText(n, "title", 20)).toBe("Deep learning gener…");
    expect(labelText(n, "short", 28, true)).toBe(n.title);
  });
  it("sizes labels in three tiers and never below the minimum", () => {
    const imp: Importance = { score: new Map(), terms: new Map(), qrank: new Map(), maxScore: 1 };
    const topic: GNode = node("t", { type: "topic" });
    const paper: GNode = node("p", { type: "paper", layer: "source" });
    expect(labelPx(topic, DEFAULT_LAB, imp, 1)).toBe(DEFAULT_LAB.t1);
    expect(labelPx(paper, DEFAULT_LAB, imp, 1)).toBe(DEFAULT_LAB.t3);
    expect(labelPx(paper, { ...DEFAULT_LAB, t3: 6 }, imp, 1)).toBe(DEFAULT_LAB.minPx);
  });
});
