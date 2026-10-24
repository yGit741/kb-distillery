import type { GNode } from "../types";
import { tierOf, type LabConfig } from "./config";
import type { Importance } from "./importance";

/** Screen box [x1, y1, x2, y2] in CSS pixels. */
export type Box = [number, number, number, number];

/** Forced labels by rank: the hovered page, the selection, their top neighbours, "Aa" types. */
export const FORCED = { hover: 0, selected: 1, near: 2, type: 3 } as const;

const STOP = new Set(["the", "a", "an", "of", "on", "and", "for", "in", "to", "with", "via", "from", "by", "at"]);
const QUESTION_LEAD = /^(does|do|is|are|can|could|what|why|how|which|when|where|should|will)\s+((is|are|do|does|there)\s+)?((the|a|an)\s+)?/i;

/**
 * Label text. "short" drops a leading article, a subtitle after ":" or " - ", and parentheses, cuts at a word
 * boundary; a question loses its question word and gets a "?" marker ("Does the low-rank bias…" -> "? Low-rank bias…").
 * The hovered page (`full`) always shows its whole title.
 */
export function labelText(n: GNode, field: LabConfig["textField"], maxChars: number, full = false): string {
  let s = field === "slug" ? n.id : n.title || n.id;
  if (full || field === "slug") return full || s.length <= maxChars ? s : `${s.slice(0, maxChars - 1)}…`;
  if (field === "title") return s.length <= maxChars ? s : `${s.slice(0, maxChars - 1)}…`;
  const question = n.type === "question";
  if (question) {
    s = s.replace(QUESTION_LEAD, "").replace(/\?$/, "");
    s = s.charAt(0).toUpperCase() + s.slice(1);
  }
  s = s.replace(/^(the|a|an)\s+/i, "").replace(/\s*[:(—–-]\s.*$/, "").replace(/\s*\(.*?\)\s*/g, " ").trim();
  if (s.length > maxChars) {
    let out = "";
    for (const w of s.split(/\s+/)) {
      if ((out + " " + w).trim().length > maxChars) break;
      out = (out + " " + w).trim();
    }
    while (out && STOP.has((out.split(" ").pop() ?? "").toLowerCase())) out = out.split(" ").slice(0, -1).join(" ");
    s = `${out || s.slice(0, maxChars)}…`;
  }
  return question ? `? ${s}` : s;
}

export function labelTier(n: GNode, cfg: LabConfig, imp: Importance): 1 | 2 | 3 {
  if (cfg.sizeMode === "quantile") {
    const q = imp.qrank.get(n.id) ?? 1;
    return q < 0.05 ? 1 : q < 0.25 ? 2 : 3;
  }
  return tierOf(n.type);
}

/** Font size in CSS px: three tiers (by type or by score), one size, or continuous by score; never below minPx. */
export function labelPx(n: GNode, cfg: LabConfig, imp: Importance, zr: number): number {
  let px: number;
  if (cfg.sizeMode === "uniform") px = cfg.base;
  else if (cfg.sizeMode === "continuous") px = cfg.base * (0.75 + 0.6 * ((imp.score.get(n.id) ?? 0) / imp.maxScore));
  else px = [0, cfg.t1, cfg.t2, cfg.t3][labelTier(n, cfg, imp)] as number;
  return Math.max(cfg.minPx, px * Math.pow(zr, cfg.zoomScale));
}

/** Offsets tried in order: above first, then below, right, left (then diagonals). */
const OFFSETS: Record<number, readonly (readonly [number, number])[]> = {
  1: [[0, 1]],
  4: [[0, -1], [0, 1], [1, 0], [-1, 0]],
  8: [[0, -1], [0, 1], [1, 0], [-1, 0], [1, -1], [1, 1], [-1, -1], [-1, 1]],
};

const overlaps = (a: Box, b: Box) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];

class Grid {
  private cells = new Map<string, { b: Box; id: string | null; node: boolean }[]>();
  constructor(private cell: number) {}
  private keys(b: Box): string[] {
    const out: string[] = [];
    for (let x = Math.floor(b[0] / this.cell); x <= Math.floor(b[2] / this.cell); x++)
      for (let y = Math.floor(b[1] / this.cell); y <= Math.floor(b[3] / this.cell); y++) out.push(`${x},${y}`);
    return out;
  }
  hit(b: Box, skip: string, labelsOnly: boolean): boolean {
    for (const k of this.keys(b)) for (const q of this.cells.get(k) ?? []) if (q.id !== skip && !(labelsOnly && q.node) && overlaps(b, q.b)) return true;
    return false;
  }
  add(b: Box, id: string | null, node = false): void {
    for (const k of this.keys(b)) {
      const list = this.cells.get(k);
      if (list) list.push({ b, id, node });
      else this.cells.set(k, [{ b, id, node }]);
    }
  }
}

export interface ScreenItem {
  n: GNode;
  sx: number;
  sy: number;
  /** node radius in CSS px */
  r: number;
}

export interface PlanInput {
  items: readonly ScreenItem[];
  width: number;
  height: number;
  /** zoom / zoom at fit */
  zr: number;
  cfg: LabConfig;
  imp: Importance;
  forced: ReadonlyMap<string, number>;
  /** pages within the focus (degree-of-interest) hops, or null when focus is off */
  hops: ReadonlyMap<string, number> | null;
  /** labels shown last frame and the offset each used */
  prev: ReadonlyMap<string, { shown: boolean; pos: number }>;
  /** boxes that block labels (region names) */
  obstacles: readonly Box[];
  suppress: boolean;
  measure: (text: string, px: number, weight: number) => number;
}

export interface Placed {
  id: string;
  n: GNode;
  text: string;
  px: number;
  weight: number;
  tier: 1 | 2 | 3;
  pos: number;
  box: Box;
  forced: boolean;
}

export interface Plan {
  placed: Placed[];
  dropped: number;
  /** on-screen candidates */
  onScreen: number;
  /** labels on screen and the share of the canvas their boxes cover (forced ones excluded) */
  shownOnScreen: number;
  coverage: number;
  minPx: number;
}

/**
 * Which labels show and where. Candidates are taken from the whole graph ("world") so panning never changes
 * them, or from the screen; forced labels first, then by score (+ a bonus for labels already shown). The budget
 * is a screen coverage, a count or a score threshold, growing as zoom^g on screen (g = 0.5 is the radical law).
 * Each label tries its previous offset first, then above/below/right/left; one that would overlap a placed label
 * (or a node, unless forced or a tier-1 label) is dropped, except the hovered page's.
 */
export function planLabels(i: PlanInput): Plan {
  const { cfg, imp, width: W, height: H, zr } = i;
  const cand: (ScreenItem & { f: number | undefined; s: number; off: boolean })[] = [];
  for (const it of i.items) {
    const off = it.sx < -40 || it.sy < -20 || it.sx > W + 40 || it.sy > H + 20;
    if (off && cfg.scope === "screen") continue;
    const f = i.forced.get(it.n.id);
    if (i.hops && f === undefined && (i.hops.get(it.n.id) ?? Infinity) > cfg.doiHops) continue;
    if (f === undefined) {
      if (i.suppress) continue;
      if (cfg.pool === "hubs" && zr < 2 && tierOf(it.n.type) !== 1) continue;
    }
    const was = i.prev.get(it.n.id);
    const bonus = was?.shown ? cfg.hysteresis : 0;
    const doi = i.hops ? cfg.doiLambda * (i.hops.get(it.n.id) ?? 0) : 0;
    cand.push({ ...it, f, off, s: (imp.score.get(it.n.id) ?? 0) + bonus - doi });
  }
  cand.sort((a, b) => (a.f ?? 9) - (b.f ?? 9) || b.s - a.s || a.n.id.localeCompare(b.n.id));

  const grid = new Grid(48);
  if (cfg.avoidNodes) for (const q of cand) grid.add([q.sx - q.r - 1, q.sy - q.r - 1, q.sx + q.r + 1, q.sy + q.r + 1], q.n.id, true);
  for (const b of i.obstacles) grid.add(b, null);

  const worldF = cfg.scope === "world" ? zr * zr : 1;
  const grow = Math.pow(zr, cfg.zoomGrowth);
  const budgetN = cfg.strategy === "count" ? Math.round(cfg.count * worldF * grow) : Infinity;
  const budgetA = cfg.strategy === "coverage" ? ((W * H * cfg.coverage) / 100) * worldF * grow : Infinity;
  const thr = cfg.strategy === "threshold" ? cfg.threshold / Math.pow(Math.max(1, zr), cfg.zoomGrowth) : -Infinity;

  const offsets = OFFSETS[cfg.positions] ?? (OFFSETS[4] as readonly (readonly [number, number])[]);
  const placed: Placed[] = [];
  let area = 0;
  let count = 0;
  let dropped = 0;
  for (const q of cand) {
    const isForced = q.f !== undefined;
    if (!isForced && (count >= budgetN || area >= budgetA || q.s < thr)) break;
    const tier = labelTier(q.n, cfg, imp);
    const px = labelPx(q.n, cfg, imp, zr);
    const weight = cfg.weightTier && tier === 1 ? 700 : 400;
    const text = labelText(q.n, cfg.textField, cfg.maxChars, q.f === FORCED.hover);
    const w = i.measure(text, px, weight);
    const h = px * 1.05;
    const prevPos = i.prev.get(q.n.id);
    const order = prevPos?.shown && offsets[prevPos.pos] ? [prevPos.pos, ...offsets.keys()] : [...offsets.keys()];
    let box: Box | null = null;
    let pos = 0;
    for (const k of order) {
      const [dx, dy] = offsets[k] as readonly [number, number];
      const cx = q.sx + dx * (q.r + 3 + (dx ? w / 2 : 0));
      const cy = q.sy + dy * (q.r + 3 + h / 2);
      const b: Box = [cx - w / 2 - cfg.pad, cy - h / 2 - cfg.pad, cx + w / 2 + cfg.pad, cy + h / 2 + cfg.pad];
      if (!cfg.declutter || q.f === FORCED.hover || !grid.hit(b, q.n.id, isForced || tier === 1)) {
        box = b;
        pos = k;
        break;
      }
    }
    if (!box) {
      dropped++;
      continue;
    }
    grid.add(box, q.n.id);
    placed.push({ id: q.n.id, n: q.n, text, px, weight, tier, pos, box, forced: isForced });
    if (!isForced) {
      count++;
      area += (box[2] - box[0]) * (box[3] - box[1]);
    }
  }
  const onBox = (b: Box) => b[2] > 0 && b[0] < W && b[3] > 0 && b[1] < H;
  const visibleLabels = placed.filter((p) => onBox(p.box));
  const cov = visibleLabels.filter((p) => !p.forced).reduce((a, p) => a + (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]), 0);
  return {
    placed,
    dropped,
    onScreen: cand.filter((q) => !q.off).length,
    shownOnScreen: visibleLabels.length,
    coverage: W * H ? (100 * cov) / (W * H) : 0,
    minPx: visibleLabels.reduce((m, p) => Math.min(m, p.px), Infinity),
  };
}
