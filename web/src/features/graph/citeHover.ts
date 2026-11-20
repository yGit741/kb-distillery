import { flag } from "@/flags";
import { withAlpha, type CanvasColors } from "./canvasTheme";
import { STATE } from "./encoding/spec";
import type { SimLink, SimNode } from "./types";

/**
 * Citations by meaning: the hovered citation. No tooltip box: the two papers' own labels complete to their full
 * titles, "cites" is written on the edge, the edge darkens and its two dots get a thin ring; the rest dims. The hover
 * band has hysteresis (enter within 6 px, leave beyond 12 px) and a short dwell, so it never flickers.
 */
export const CITE_ENTER_PX = 6;
export const CITE_LEAVE_PX = 12;
/** another edge takes over only when it is this much closer than the current one */
export const CITE_SWITCH_PX = 4;
export const CITE_DWELL_MS = 120;
export const CITE_HOLD_MS = 80;

type Pt = { x: number; y: number };
const at = (e: SimLink["source"]): Pt | null => (typeof e === "object" && e && e.x != null && e.y != null ? { x: e.x, y: e.y } : null);
const ctrlOf = (l: SimLink): Pt | null => {
  const c = (l as SimLink & { __controlPoints?: number[] | null }).__controlPoints;
  return c && c.length >= 2 ? { x: c[0]!, y: c[1]! } : null;
};

/** A point on the link's drawn curve (force-graph's quadratic bezier when the link bends), t in 0..1. */
export function linkPoint(l: SimLink, t: number): Pt | null {
  const a = at(l.source);
  const b = at(l.target);
  if (!a || !b) return null;
  const c = ctrlOf(l);
  if (!c) return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
  const u = 1 - t;
  return { x: u * u * a.x + 2 * u * t * c.x + t * t * b.x, y: u * u * a.y + 2 * u * t * c.y + t * t * b.y };
}

/** Distance (graph units) from a point to the link's curve, sampled; Infinity when the link is not placed yet. */
export function linkDistance(l: SimLink, x: number, y: number, samples = 24): number {
  let best = Infinity;
  for (let i = 0; i <= samples; i++) {
    const p = linkPoint(l, i / samples);
    if (!p) return Infinity;
    best = Math.min(best, Math.hypot(p.x - x, p.y - y));
  }
  return best;
}

/** True when the point is farther than `pad` from the box around the link's ends and bend: a cheap first test. */
function outside(l: SimLink, x: number, y: number, pad: number): boolean {
  const a = at(l.source);
  const b = at(l.target);
  if (!a || !b) return true;
  const c = ctrlOf(l) ?? a;
  return x < Math.min(a.x, b.x, c.x) - pad || x > Math.max(a.x, b.x, c.x) + pad || y < Math.min(a.y, b.y, c.y) - pad || y > Math.max(a.y, b.y, c.y) + pad;
}

const isCite = (l: SimLink) => l.kind === "cites";

/**
 * The next hovered link given the current one, the pointer (graph units) and the zoom: enter within CITE_ENTER_PX,
 * stay until beyond CITE_LEAVE_PX, switch only to an edge CITE_SWITCH_PX closer. Pixel bands are divided by the zoom.
 * `accept` names the links that can light up: the citations (Citations by meaning), or every edge (flag edge-select).
 */
export function pickCite(
  links: readonly SimLink[],
  current: SimLink | null,
  x: number,
  y: number,
  zoom: number,
  accept: (l: SimLink) => boolean = isCite,
): SimLink | null {
  const k = Math.max(zoom, 0.05);
  const pad = CITE_LEAVE_PX / k;
  let best: SimLink | null = null;
  let bestD = Infinity;
  for (const l of links) {
    if (!accept(l) || (l !== current && outside(l, x, y, pad))) continue;
    const d = linkDistance(l, x, y);
    if (d < bestD) {
      best = l;
      bestD = d;
    }
  }
  if (current) {
    const dc = linkDistance(current, x, y);
    if (dc <= CITE_LEAVE_PX / k) {
      return best && best !== current && bestD <= CITE_ENTER_PX / k && bestD + CITE_SWITCH_PX / k < dc ? best : current;
    }
  }
  return best && bestD <= CITE_ENTER_PX / k ? best : null;
}

/** Words of `text` wrapped to `width` (in the context's current font). */
function wrap(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const out: string[] = [];
  let line = "";
  for (const w of text.split(/\s+/)) {
    const next = line ? `${line} ${w}` : w;
    if (line && ctx.measureText(next).width > width) {
      out.push(line);
      line = w;
    } else line = next;
  }
  if (line) out.push(line);
  return out;
}

/**
 * Draw the hovered citation on top: the edge in label ink at 1.5 px, a thin ring on its two dots, "cites" at the
 * curve's middle (horizontal, haloed; beside a short edge), and each paper's full title: the higher paper's above
 * its dot, the lower one's below, so the two never meet. Sizes are screen pixels (divided by `scale`).
 */
export function drawCite(ctx: CanvasRenderingContext2D, l: SimLink, scale: number, colors: CanvasColors, radiusOf: (n: SimNode) => number): void {
  drawEdges(ctx, [l], scale, colors, radiusOf, () => "cites", () => true);
}

/**
 * Draw lit edges on top, each as a hovered citation is drawn: the edge in label ink, its words at the middle (`word`),
 * an arrow at the target where the edge reads one way (`arrow`, flag graph-corners), a thin ring on every page it
 * touches and each page's full title once: above its dot when it is the higher end of its first edge, else below.
 */
export function drawEdges(
  ctx: CanvasRenderingContext2D,
  links: readonly SimLink[],
  scale: number,
  colors: CanvasColors,
  radiusOf: (n: SimNode) => number,
  word: (l: SimLink) => string,
  arrow: (l: SimLink) => boolean,
  /** The line's width in screen pixels: 1.5 for a lit edge, wider for a shortest path (./pathDraw). */
  width = 1.5,
  /** pages that already wear a ring (the selected ones): they get no second one */
  ringed: (n: SimNode) => boolean = () => false,
): void {
  const px = (v: number) => v / scale;
  const ends = new Map<string, { n: SimNode; above: boolean }>();
  ctx.save();
  for (const l of links) {
    const a = l.source as SimNode;
    const b = l.target as SimNode;
    if (!at(a) || !at(b)) continue;
    drawEdgeLine(ctx, l, scale, colors, radiusOf, word(l), arrow(l), width);
    const [up, down] = a.y! <= b.y! ? [a, b] : [b, a];
    if (!ends.has(up.id)) ends.set(up.id, { n: up, above: true });
    if (!ends.has(down.id)) ends.set(down.id, { n: down, above: false });
  }
  // the rings of the pages the edges touch, where the selection ring would sit (the arrow tips end on it)
  for (const { n } of ends.values()) {
    if (ringed(n)) continue;
    ctx.beginPath();
    ctx.arc(n.x!, n.y!, radiusOf(n) + px(STATE.gap), 0, Math.PI * 2);
    ctx.strokeStyle = withAlpha(colors.text, 0.6);
    ctx.lineWidth = px(1.5);
    ctx.stroke();
  }
  // each page's full title, once
  ctx.font = `500 ${px(12)}px ${colors.font}`;
  ctx.textAlign = "center";
  ctx.fillStyle = colors.text;
  const lineH = px(15);
  for (const { n, above } of ends.values()) {
    const lines = wrap(ctx, n.title || n.id, px(200));
    if (above) {
      ctx.textBaseline = "bottom";
      lines.forEach((t, i) => halo(ctx, colors, scale, t, n.x!, n.y! - radiusOf(n) - px(6) - (lines.length - 1 - i) * lineH));
    } else {
      ctx.textBaseline = "top";
      lines.forEach((t, i) => halo(ctx, colors, scale, t, n.x!, n.y! + radiusOf(n) + px(6) + i * lineH));
    }
  }
  ctx.restore();
}

/**
 * The standing words of a sparse graph's edges (./edgeWords): each edge's word at its curve's middle, small and
 * muted, along no edge shorter than the word. A word that would overlap one already written is left out.
 */
export function drawEdgeWords(ctx: CanvasRenderingContext2D, links: readonly SimLink[], scale: number, colors: CanvasColors, word: (l: SimLink) => string): void {
  const px = (v: number) => v / scale;
  const placed: { x0: number; y0: number; x1: number; y1: number }[] = [];
  ctx.save();
  ctx.font = `500 ${px(10)}px ${colors.font}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = withAlpha(colors.text, 0.55);
  for (const l of links) {
    const a = at(l.source);
    const b = at(l.target);
    const mid = linkPoint(l, 0.5);
    const text = word(l);
    if (!a || !b || !mid || !text) continue;
    const w = ctx.measureText(text).width;
    if (Math.hypot(b.x - a.x, b.y - a.y) < w + px(24)) continue;
    const box = { x0: mid.x - w / 2 - px(2), y0: mid.y - px(7), x1: mid.x + w / 2 + px(2), y1: mid.y + px(7) };
    if (placed.some((q) => box.x0 < q.x1 && box.x1 > q.x0 && box.y0 < q.y1 && box.y1 > q.y0)) continue;
    placed.push(box);
    halo(ctx, colors, scale, text, mid.x, mid.y);
  }
  ctx.restore();
}

/** Text with a background halo, so it reads over edges and dots. */
function halo(ctx: CanvasRenderingContext2D, colors: CanvasColors, scale: number, text: string, x: number, y: number): void {
  ctx.lineJoin = "round";
  ctx.strokeStyle = colors.background;
  ctx.lineWidth = 3 / scale;
  ctx.strokeText(text, x, y);
  ctx.fillText(text, x, y);
}

/** One lit edge: the line (under its two pages, flag graph-corners), its arrow and its words. */
function drawEdgeLine(ctx: CanvasRenderingContext2D, l: SimLink, scale: number, colors: CanvasColors, radiusOf: (n: SimNode) => number, words: string, arrow: boolean, width = 1.5): void {
  const a = l.source as SimNode;
  const b = l.target as SimNode;
  const pa = at(a)!;
  const pb = at(b)!;
  const px = (v: number) => v / scale;
  ctx.save();
  const c = ctrlOf(l);
  // flag graph-corners: the edge runs under the two pages, never across them: it is clipped at each page's ring and,
  // where it reads one way, ends in a small arrow at its target's rim
  const under = flag("graph-corners");
  const rimA = radiusOf(a) + px(STATE.gap);
  const rimB = radiusOf(b) + px(STATE.gap);
  if (under) {
    ctx.save();
    ctx.beginPath();
    ctx.rect(-1e7, -1e7, 2e7, 2e7);
    ctx.moveTo(pa.x + rimA, pa.y);
    ctx.arc(pa.x, pa.y, rimA, 0, Math.PI * 2);
    ctx.moveTo(pb.x + rimB, pb.y);
    ctx.arc(pb.x, pb.y, rimB, 0, Math.PI * 2);
    ctx.clip("evenodd");
  }
  ctx.beginPath();
  ctx.moveTo(pa.x, pa.y);
  if (c) ctx.quadraticCurveTo(c.x, c.y, pb.x, pb.y);
  else ctx.lineTo(pb.x, pb.y);
  ctx.strokeStyle = withAlpha(colors.text, width > 1.5 ? 0.9 : 0.75);
  ctx.lineWidth = px(width);
  ctx.stroke();
  if (under) {
    ctx.restore();
    if (arrow) {
      // along the edge's last direction, its tip on the target's ring
      const from = c ?? pa;
      const d = Math.hypot(pb.x - from.x, pb.y - from.y) || 1;
      const ux = (pb.x - from.x) / d;
      const uy = (pb.y - from.y) / d;
      const tx = pb.x - ux * rimB;
      const ty = pb.y - uy * rimB;
      const len = px(7);
      const half = px(3.5);
      ctx.beginPath();
      ctx.moveTo(tx, ty);
      ctx.lineTo(tx - ux * len + uy * half, ty - uy * len - ux * half);
      ctx.lineTo(tx - ux * len - uy * half, ty - uy * len + ux * half);
      ctx.closePath();
      ctx.fillStyle = withAlpha(colors.text, 0.75);
      ctx.fill();
    }
  }
  // the words on the edge: at the curve's middle; on a short edge, just beside it so neither dot covers them
  const mid = linkPoint(l, 0.5);
  if (mid && words) {
    ctx.font = `500 ${px(11)}px ${colors.font}`;
    ctx.textBaseline = "middle";
    ctx.fillStyle = withAlpha(colors.text, 0.85);
    const short = Math.hypot(pb.x - pa.x, pb.y - pa.y) * scale < 60;
    ctx.textAlign = short ? "left" : "center";
    halo(ctx, colors, scale, words, short ? mid.x + px(9) : mid.x, mid.y);
  }
  ctx.restore();
}
