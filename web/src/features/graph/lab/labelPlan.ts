import { shortTitle, wrapLabel } from "../encoding/label";
import type { GNode } from "../types";
import { tierOf, type LabConfig } from "./config";
import type { Importance } from "./importance";

/** Screen box [x1, y1, x2, y2] in CSS pixels. */
export type Box = [number, number, number, number];

/** The label words live in the shared encoding (one label style on every graph). */
export { labelText, shortTitle, wrapLabel } from "../encoding/label";

/** Forced labels by rank: the hovered page, the selection, their top neighbours, "Aa" types. */
export const FORCED = { hover: 0, selected: 1, near: 2, type: 3 } as const;

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
  // node: a node disc or a soft obstacle; both yield to forced and tier-1 labels
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
  /** screen furniture (the page-type strip): blocks ordinary labels only, never a forced or tier-1 one */
  softObstacles?: readonly Box[];
  suppress: boolean;
  measure: (text: string, px: number, weight: number) => number;
}

export interface Placed {
  id: string;
  n: GNode;
  /** the lines joined by a space */
  text: string;
  lines: string[];
  px: number;
  /** line height in CSS px (the box is lines × lineH plus padding) */
  lineH: number;
  weight: number;
  tier: 1 | 2 | 3;
  pos: number;
  box: Box;
  forced: boolean;
  /** the hovered page or the selection: only these get the pill (neighbours and "Aa" types stay plain) */
  focus: boolean;
  /** placed off the node on a ring, joined to it by a leader line */
  leader: boolean;
  /** node centre on screen */
  anchor: [number, number];
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

/** Unit directions of the ring a squeezed-out forced label moves to: the eight compass points. */
const RING = OFFSETS[8] as readonly (readonly [number, number])[];
/** The hovered or clicked page shows its whole title, wrapped: width and lines. */
const FOCUS_FULL = { width: 220, lines: 3 } as const;

/**
 * Which labels show and where. Candidates are taken from the whole graph ("world") so panning never changes
 * them, or from the screen; forced labels first, then by score (+ a bonus for labels already shown). The budget
 * is a screen coverage, a count or a score threshold, growing as zoom^g on screen (g = 0.5 is the radical law).
 * Text wraps to the tier's pixel width (tier 3 stays one line); questions hide, cut short or show by
 * `questionLabels`, and a hovered or clicked one shows its whole title. Each label tries its previous offset
 * first, then above/below/right/left; a box pushed off the canvas tries the mirrored side first (`edgeFlip`). One
 * that would overlap a placed label (or a node, unless forced or a tier-1 label) is dropped, except a forced
 * label, which moves out on a ring with a leader line (`leaderLines`) before it is given up.
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
      if (cfg.questionLabels === "none" && it.n.type === "question") continue;
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
  for (const b of i.softObstacles ?? []) grid.add(b, null, true);

  const worldF = cfg.scope === "world" ? zr * zr : 1;
  const grow = Math.pow(zr, cfg.zoomGrowth);
  const budgetN = cfg.strategy === "count" ? Math.round(cfg.count * worldF * grow) : Infinity;
  const budgetA = cfg.strategy === "coverage" ? ((W * H * cfg.coverage) / 100) * worldF * grow : Infinity;
  const thr = cfg.strategy === "threshold" ? cfg.threshold / Math.pow(Math.max(1, zr), cfg.zoomGrowth) : -Infinity;

  const offsets = OFFSETS[cfg.positions] ?? (OFFSETS[4] as readonly (readonly [number, number])[]);
  const inside = (b: Box) => b[0] >= 0 && b[1] >= 0 && b[2] <= W && b[3] <= H;
  const placed: Placed[] = [];
  let area = 0;
  let count = 0;
  let dropped = 0;
  for (const q of cand) {
    const isForced = q.f !== undefined;
    if (!isForced && (count >= budgetN || area >= budgetA || q.s < thr)) break;
    const tier = labelTier(q.n, cfg, imp);
    const px = labelPx(q.n, cfg, imp, zr);
    // emphasis by role, never by box: headline tier bold, the focus (hover, selection) bold, its neighbours semibold
    const focus = q.f !== undefined && q.f <= FORCED.selected;
    const near = q.f === FORCED.near;
    const weight = (cfg.weightTier && tier === 1) || focus ? 700 : near ? 600 : 400;
    const m = (t: string) => i.measure(t, px, weight);
    // text: the focus shows its whole title wrapped; a neighbour wraps to two lines; the rest by tier (tier 3 one line)
    const tierChars = tier === 3 ? cfg.charsT3 : cfg.maxChars;
    let lines: string[];
    if (focus) lines = wrapLabel(shortTitle(q.n, cfg.textField, true), FOCUS_FULL.width, FOCUS_FULL.lines, m, cfg.maxChars);
    else if (near) lines = wrapLabel(shortTitle(q.n, cfg.textField), Math.max(cfg.wrapT2, 120), 2, m, cfg.maxChars);
    // a question gets an idea's room (two wrapped lines); the overlap check still drops one with no space
    else if (q.n.type === "question" && cfg.questionLabels !== "full" && cfg.textField === "short")
      lines = wrapLabel(shortTitle(q.n, cfg.textField), cfg.wrapT2, cfg.maxLines, m, Math.max(cfg.charsQuestion, tierChars));
    else if (tier === 3) lines = wrapLabel(shortTitle(q.n, cfg.textField), cfg.wrapT3, 1, m, cfg.charsT3);
    else lines = wrapLabel(shortTitle(q.n, cfg.textField), tier === 1 ? cfg.wrapT1 : cfg.wrapT2, cfg.maxLines, m, cfg.maxChars);
    const w = Math.max(...lines.map(m));
    const lineH = px * 1.15;
    const h = lines.length * lineH;
    const boxAt = (dx: number, dy: number, d: number): Box => {
      const cx = q.sx + dx * (d + (dx ? w / 2 : 0));
      const cy = q.sy + dy * (d + (dy ? h / 2 : 0));
      return [cx - w / 2 - cfg.pad, cy - h / 2 - cfg.pad, cx + w / 2 + cfg.pad, cy + h / 2 + cfg.pad];
    };
    const free = (b: Box) => !cfg.declutter || !grid.hit(b, q.n.id, isForced || tier === 1);
    const prevPos = i.prev.get(q.n.id);
    const order = prevPos?.shown && offsets[prevPos.pos] ? [prevPos.pos, ...offsets.keys()] : [...offsets.keys()];
    let box: Box | null = null;
    let pos = 0;
    let leader = false;
    for (const k of order) {
      const [dx, dy] = offsets[k] as readonly [number, number];
      const b = boxAt(dx, dy, q.r + 3);
      // a node on the canvas whose box leaves it: the mirrored side first
      if (cfg.edgeFlip && !inside(b) && q.sx >= 0 && q.sx <= W && q.sy >= 0 && q.sy <= H) {
        const mb = boxAt(-dx, -dy, q.r + 3);
        if (inside(mb) && free(mb)) {
          box = mb;
          const mk = offsets.findIndex(([ox, oy]) => ox === -dx && oy === -dy);
          pos = mk >= 0 ? mk : k;
          break;
        }
      }
      if (free(b)) {
        box = b;
        pos = k;
        break;
      }
    }
    // forced against forced: out on a ring, one to three box heights off the node (the hover label always)
    if (!box && isForced && (cfg.leaderLines || q.f === FORCED.hover)) {
      ring: for (let k = 1; k <= 3; k++)
        for (const [dx, dy] of RING) {
          const b = boxAt(dx, dy, q.r + 3 + h * k);
          if (free(b)) {
            box = b;
            leader = true;
            break ring;
          }
        }
    }
    // the hovered page is never without its label: its first slot, overlap or not
    if (!box && q.f === FORCED.hover) {
      const [dx, dy] = offsets[order[0] as number] as readonly [number, number];
      box = boxAt(dx, dy, q.r + 3);
      pos = order[0] as number;
    }
    if (!box) {
      dropped++;
      continue;
    }
    grid.add(box, q.n.id);
    placed.push({ id: q.n.id, n: q.n, text: lines.join(" "), lines, px, lineH, weight, tier, pos, box, forced: isForced, focus: q.f !== undefined && q.f <= FORCED.selected, leader, anchor: [q.sx, q.sy] });
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
