import { withAlpha, type CanvasColors } from "./canvasTheme";
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

/**
 * The next hovered link given the current one, the pointer (graph units) and the zoom: enter within CITE_ENTER_PX,
 * stay until beyond CITE_LEAVE_PX, switch only to an edge CITE_SWITCH_PX closer. Pixel bands are divided by the zoom.
 */
export function pickCite(links: readonly SimLink[], current: SimLink | null, x: number, y: number, zoom: number): SimLink | null {
  const k = Math.max(zoom, 0.05);
  let best: SimLink | null = null;
  let bestD = Infinity;
  for (const l of links) {
    if (l.kind !== "cites") continue;
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
  const a = l.source as SimNode;
  const b = l.target as SimNode;
  const pa = at(a);
  const pb = at(b);
  if (!pa || !pb) return;
  const px = (v: number) => v / scale;
  ctx.save();
  // the edge
  ctx.beginPath();
  ctx.moveTo(pa.x, pa.y);
  const c = ctrlOf(l);
  if (c) ctx.quadraticCurveTo(c.x, c.y, pb.x, pb.y);
  else ctx.lineTo(pb.x, pb.y);
  ctx.strokeStyle = withAlpha(colors.text, 0.75);
  ctx.lineWidth = px(1.5);
  ctx.stroke();
  // the two dots' rings
  for (const n of [a, b]) {
    ctx.beginPath();
    ctx.arc(n.x!, n.y!, radiusOf(n) + px(2), 0, Math.PI * 2);
    ctx.strokeStyle = withAlpha(colors.text, 0.8);
    ctx.lineWidth = px(2);
    ctx.stroke();
  }
  const halo = (text: string, x: number, y: number) => {
    ctx.lineJoin = "round";
    ctx.strokeStyle = colors.background;
    ctx.lineWidth = px(3);
    ctx.strokeText(text, x, y);
    ctx.fillText(text, x, y);
  };
  // "cites" on the edge: at the curve's middle; on a short edge, just beside it so neither dot covers it
  const mid = linkPoint(l, 0.5);
  if (mid) {
    ctx.font = `500 ${px(11)}px ${colors.font}`;
    ctx.textBaseline = "middle";
    ctx.fillStyle = withAlpha(colors.text, 0.85);
    const short = Math.hypot(pb.x - pa.x, pb.y - pa.y) * scale < 60;
    ctx.textAlign = short ? "left" : "center";
    halo("cites", short ? mid.x + px(9) : mid.x, mid.y);
  }
  // the two full titles: the higher paper's above its dot, the lower one's below, so the two never meet
  ctx.font = `500 ${px(12)}px ${colors.font}`;
  ctx.textAlign = "center";
  ctx.fillStyle = colors.text;
  const lineH = px(15);
  const titleOf = (n: SimNode) => n.title || n.id;
  const [up, down] = a.y! <= b.y! ? [a, b] : [b, a];
  const lu = wrap(ctx, titleOf(up), px(200));
  const ld = wrap(ctx, titleOf(down), px(200));
  ctx.textBaseline = "bottom";
  lu.forEach((t, i) => halo(t, up.x!, up.y! - radiusOf(up) - px(6) - (lu.length - 1 - i) * lineH));
  ctx.textBaseline = "top";
  ld.forEach((t, i) => halo(t, down.x!, down.y! + radiusOf(down) + px(6) + i * lineH));
  ctx.restore();
}
