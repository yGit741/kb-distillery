/**
 * Citations by meaning (flag citations-meaning): where each paper sits in the Citations view.
 *
 * Papers are grouped by their embedding topic. The topics go round a ring in their own order, each sector as wide
 * as its share of papers. A topic's uncited papers (no `cites` link either way) are pinned as one tight spiral on the
 * outer rim of its sector; its cited papers are pulled, gently, toward the inner end of the sector, so the citation
 * web fills the middle and never runs through a clump. The topic's name sits on the clump's outer side.
 */

export interface RimInput {
  id: string;
  /** citations given plus received, within the drawn papers */
  degree: number;
}

export interface RimLabel {
  name: string;
  count: number;
  /** graph coordinates of the label's anchor, on the clump's outer side */
  x: number;
  y: number;
  /** which way the text runs from the anchor: away from the centre */
  align: "left" | "right" | "center";
  /** the label's line sits above (-1) or below (1) the anchor */
  baseline: -1 | 0 | 1;
}

export interface RimLayout {
  /** uncited papers: fixed positions in their clump */
  pins: Map<string, [number, number]>;
  /** cited papers: the point their topic pulls them toward */
  pull: Map<string, [number, number]>;
  labels: RimLabel[];
  /** one disc per clump (its spiral plus a margin): no cited paper may enter it */
  discs: { x: number; y: number; r: number }[];
}

const GOLDEN = 2.399963229728653; // radians between two seeds of a sunflower

/**
 * The layout for `papers`, given each paper's topic (`topicOf`, undefined = no vector: grouped as its own topic),
 * the topic names, and the drawn node diameter `dot` (graph units). `order` is the topics' ring order (their
 * embedding order, so neighbours in meaning stay neighbours on the ring).
 */
export function rimLayout(
  papers: readonly RimInput[],
  topicOf: (id: string) => number | undefined,
  names: ReadonlyMap<number, string>,
  dot: number,
  order?: readonly number[],
): RimLayout {
  const NONE = -1;
  const groups = new Map<number, RimInput[]>();
  for (const p of papers) {
    const t = topicOf(p.id) ?? NONE;
    if (!groups.has(t)) groups.set(t, []);
    groups.get(t)!.push(p);
  }
  const ids = [...groups.keys()];
  const ring = [...(order ?? []).filter((t) => groups.has(t)), ...ids.filter((t) => !(order ?? []).includes(t)).sort((a, b) => a - b)];
  const total = papers.length || 1;
  // the web's radius grows with the cited papers; the clumps sit a clear margin outside it
  const cited = papers.filter((p) => p.degree > 0).length;
  const spacing = dot * 1.25; // centre to centre inside a clump: dots just apart
  const inner = Math.max(dot * 8, Math.sqrt(cited) * dot * 4);
  const pins = new Map<string, [number, number]>();
  const pull = new Map<string, [number, number]>();
  const labels: RimLabel[] = [];
  const discs: { x: number; y: number; r: number }[] = [];
  let start = -Math.PI / 2;
  // each topic's share of the ring follows its paper count, with a floor so a small topic still has room
  const weight = (t: number) => Math.max(groups.get(t)!.length, total * 0.08);
  const weights = ring.reduce((a, t) => a + weight(t), 0) || 1;
  const sweepOf = (t: number) => (weight(t) / weights) * Math.PI * 2;
  // the clump radius of the largest topic sets one rim radius for all, so the clumps form one even ring
  const clumpR = (n: number) => Math.sqrt(n + 0.5) * spacing * 0.56;
  const biggest = Math.max(0, ...ring.map((t) => groups.get(t)!.filter((p) => p.degree === 0).length));
  // ... and far enough out that two neighbouring clumps never touch: each sector's arc must hold its clump
  let rim = inner + dot * 4 + clumpR(biggest);
  for (const t of ring) {
    const m = groups.get(t)!;
    const need = (2 * clumpR(m.filter((p) => p.degree === 0).length) + dot * 3) / sweepOf(t);
    rim = Math.max(rim, need);
  }
  for (const t of ring) {
    const members = groups.get(t)!;
    const sweep = sweepOf(t);
    const mid = start + sweep / 2;
    start += sweep;
    const cos = Math.cos(mid);
    const sin = Math.sin(mid);
    const orphans = members.filter((p) => p.degree === 0).sort((a, b) => (a.id < b.id ? -1 : 1));
    // cited papers: toward the inner part of their sector
    for (const p of members) if (p.degree > 0) pull.set(p.id, [cos * inner * 0.4, sin * inner * 0.4]);
    // uncited papers: a sunflower centred on the rim
    const cx = cos * rim;
    const cy = sin * rim;
    orphans.forEach((p, i) => {
      const r = Math.sqrt(i + 0.5) * spacing * 0.56;
      pins.set(p.id, [cx + r * Math.cos(i * GOLDEN), cy + r * Math.sin(i * GOLDEN)]);
    });
    if (orphans.length) discs.push({ x: cx, y: cy, r: clumpR(orphans.length) + dot * 1.5 });
    // the name on the clump's outer side, running away from the centre
    const out = clumpR(orphans.length) + dot * 1.5;
    const lx = cx + cos * out;
    const ly = cy + sin * out;
    labels.push({
      name: t === NONE ? "No vector" : (names.get(t) ?? `Topic ${t + 1}`),
      count: members.length,
      x: lx,
      y: ly,
      align: Math.abs(cos) < 0.3 ? "center" : cos > 0 ? "left" : "right",
      baseline: Math.abs(cos) < 0.3 ? (sin > 0 ? 1 : -1) : 0,
    });
  }
  return { pins, pull, labels, discs };
}
