import { node } from "../fixtures";
import type { GNode } from "../types";
import { DEFAULT_LAB, type LabConfig } from "./config";
import type { Importance } from "./importance";
import { FORCED, labelPx, labelText, planLabels, shortTitle, wrapLabel, type PlanInput, type ScreenItem } from "./labelPlan";

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

const disjoint = (a: { box: number[] }, b: { box: number[] }) => !(a.box[0]! < b.box[2]! && a.box[2]! > b.box[0]! && a.box[1]! < b.box[3]! && a.box[3]! > b.box[1]!);

describe("wrapped labels", () => {
  const m = (t: string) => measure(t, 10);
  const long = node("t", { type: "topic", title: "Deep nets learn a low rank bias under gradient flow dynamics" });
  it("wraps at a word, within the lines allowed, with an ellipsis on the last line", () => {
    const lines = wrapLabel("alpha beta gamma delta epsilon", 80, 3, m, 28);
    expect(lines).toEqual(["alpha beta", "gamma delta", "epsilon"]);
    for (const l of lines) expect(m(l)).toBeLessThanOrEqual(80);
    expect(wrapLabel("alpha beta gamma delta epsilon", 80, 2, m, 28)).toEqual(["alpha beta", "gamma delta…"]);
    expect(wrapLabel("bias of the gradient flow", 90, 1, m, 28)).toEqual(["bias…"]);
  });
  it("never splits a word and falls back to the character cut at width 0", () => {
    expect(wrapLabel("supercalifragilistic word", 30, 2, m, 28)).toEqual(["supercalifragilistic", "word"]);
    expect(wrapLabel("supercalifragilistic word", 60, 1, m, 8)).toEqual(["supercal…"]);
    expect(wrapLabel("", 60, 2, m, 28)).toEqual([""]);
    expect(wrapLabel("   ", 60, 2, m, 28)).toEqual(["   "]);
    const p = node("p", { type: "paper", title: "Deep learning generalizes: a study of the implicit bias of gradient descent" });
    expect(wrapLabel(shortTitle(p, "short"), 0, 1, m, 28)).toEqual([labelText(p, "short", 28)]);
    expect(wrapLabel(shortTitle(long, "short"), 0, 1, m, 28)).toEqual([labelText(long, "short", 28)]);
  });
  it("a long tier-1 title takes two lines and a box two line heights tall", () => {
    const p = planLabels(input({ items: [{ n: long, sx: 300, sy: 300, r: 6 }], imp: { score: new Map([["t", 1]]), terms: new Map(), qrank: new Map(), maxScore: 1 }, cfg: { strategy: "all" } }));
    const l = p.placed[0]!;
    expect(l.lines).toHaveLength(2);
    expect(l.lines.every((x) => measure(x, l.px) <= DEFAULT_LAB.wrapT1)).toBe(true);
    expect(l.box[3] - l.box[1]).toBeCloseTo(2 * l.px * 1.15 + 2 * DEFAULT_LAB.pad, 5);
    expect(l.text).toBe(l.lines.join(" "));
  });
  it("tier 3 stays on one line of at most charsT3 characters", () => {
    const src = node("s", { type: "paper", layer: "source", title: "A very long paper title about implicit regularization and such" });
    const p = planLabels(input({ items: [{ n: src, sx: 300, sy: 300, r: 4 }], imp: { score: new Map([["s", 1]]), terms: new Map(), qrank: new Map(), maxScore: 1 }, cfg: { strategy: "all" } }));
    expect(p.placed[0]!.lines).toHaveLength(1);
    expect(p.placed[0]!.lines[0]!.length).toBeLessThanOrEqual(DEFAULT_LAB.charsT3);
  });
  const q = node("q-x", { type: "question", title: "Does the low-rank bias of depth need gradient flow to emerge in practice?" });
  const qImp = { score: new Map([["q-x", 1]]), terms: new Map(), qrank: new Map(), maxScore: 1 };
  it("questions: hidden by default, cut at charsQuestion with the ? marker when short, whole title wrapped when clicked", () => {
    const base = { items: [{ n: q, sx: 400, sy: 300, r: 5 }], imp: qImp };
    expect(planLabels(input({ ...base, cfg: { strategy: "all" } })).placed).toHaveLength(0);
    const short = planLabels(input({ ...base, cfg: { strategy: "all", questionLabels: "short" } })).placed[0]!;
    expect(short.lines).toHaveLength(1);
    expect(short.text.startsWith("? ")).toBe(true);
    expect(short.text.length).toBeLessThanOrEqual(DEFAULT_LAB.charsQuestion + 3);
    const sel = planLabels(input({ ...base, forced: new Map([["q-x", FORCED.selected]]), cfg: { strategy: "all" } })).placed[0]!;
    expect(sel.forced).toBe(true);
    expect(sel.text).toBe(q.title);
    expect(sel.lines.length).toBeLessThanOrEqual(3);
    expect(sel.lines.every((x) => measure(x, sel.px) <= 220)).toBe(true);
  });
  it("flips a label back onto the canvas from the edge", () => {
    const g = grid(1, 60);
    const items = [{ ...g.items[0]!, sx: 10, sy: 300 }];
    const prev = new Map([["idea-000", { shown: true, pos: 3 }]]); // left, off the canvas
    expect(planLabels(input({ items, imp: g.imp, prev, cfg: { strategy: "all", edgeFlip: false } })).placed[0]!.pos).toBe(3);
    const flipped = planLabels(input({ items, imp: g.imp, prev, cfg: { strategy: "all" } })).placed[0]!;
    expect(flipped.pos).toBe(2);
    expect(flipped.box[0]).toBeGreaterThanOrEqual(0);
  });
  it("two forced labels squeezed together are both placed, the second on a leader", () => {
    const a = node("a", { type: "idea", title: "Alpha concept" });
    const b = node("b", { type: "idea", title: "Beta concept" });
    const imp = { score: new Map([["a", 1], ["b", 0.9]]), terms: new Map(), qrank: new Map(), maxScore: 1 };
    const forced = new Map([["a", FORCED.near], ["b", FORCED.near]]);
    const items = [{ n: a, sx: 300, sy: 300, r: 4 }, { n: b, sx: 306, sy: 300, r: 4 }];
    const p = planLabels(input({ items, imp, forced, cfg: { strategy: "all", positions: 1 } }));
    expect(p.placed.map((x) => x.id)).toEqual(["a", "b"]);
    expect(p.placed[0]!.leader).toBe(false);
    expect(p.placed[1]!.leader).toBe(true);
    expect(disjoint(p.placed[0]!, p.placed[1]!)).toBe(true);
    expect(planLabels(input({ items, imp, forced, cfg: { strategy: "all", positions: 1, leaderLines: false } })).placed).toHaveLength(1);
  });
  it("the hover label is always placed, even with leader lines off and every slot taken", () => {
    const g = grid(100, 14);
    const forced = new Map<string, number>([["idea-050", FORCED.hover], ["idea-051", FORCED.near], ["idea-049", FORCED.near], ["idea-030", FORCED.near], ["idea-070", FORCED.near]]);
    const p = planLabels(input({ items: g.items, imp: g.imp, forced, cfg: { strategy: "all", leaderLines: false, positions: 1 } }));
    expect(p.placed.some((x) => x.id === "idea-050")).toBe(true);
    const obstacles = [[0, 0, 1200, 800] as [number, number, number, number]];
    const walled = planLabels(input({ items: grid(1, 60).items, imp: grid(1, 60).imp, forced: new Map([["idea-000", FORCED.hover]]), obstacles, cfg: { strategy: "all" } }));
    expect(walled.placed.map((x) => x.id)).toEqual(["idea-000"]);
  });
  it("the hover label never overlaps another", () => {
    const p = planLabels(input({ items: grid(100, 14).items, forced: new Map([["idea-050", FORCED.hover]]), cfg: { strategy: "all" } }));
    const h = p.placed.find((x) => x.id === "idea-050")!;
    expect(h).toBeDefined();
    for (const o of p.placed) if (o !== h) expect(disjoint(h, o)).toBe(true);
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
