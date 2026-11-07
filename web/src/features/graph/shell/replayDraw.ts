import { withAlpha, type CanvasColors } from "../canvasTheme";
import type { ReplayView } from "./replay";

/**
 * Opacity of the pages the focus leaves dim (the trail or the cited pages stay lit). On the dark canvas a mark's
 * colours are luminous, so the same alpha reads far less dim than on white: dark goes lower to match light.
 */
export const LIT_DIM = { light: 0.3, dark: 0.16 } as const;

export interface ReplayDrawing {
  view: ReplayView;
  candidates: ReadonlySet<string>;
  missed: ReadonlySet<string>;
  bad: ReadonlySet<string>;
}

/**
 * The replay's marks around a page (flag `spark-chat`), drawn over its type mark so type stays the shape:
 * seen = a thin hollow ring, read = a filled ring, cited = the accent, one link away and not read = dashed,
 * the step being looked at = an outer accent ring. A mark the reader placed (missed, bad citation) is a heavier dash.
 * Sizes are screen px (divided by the zoom), so the trail reads at any zoom.
 */
export function drawReplayMark(ctx: CanvasRenderingContext2D, id: string, x: number, y: number, r: number, scale: number, alpha: number, d: ReplayDrawing, c: CanvasColors): void {
  const role = d.view.roles.get(id);
  const bad = d.bad.has(id);
  const missed = d.missed.has(id);
  const maybe = d.candidates.has(id);
  const ring = (rr: number, width: number, color: string, dash?: number) => {
    ctx.beginPath();
    ctx.arc(x, y, rr, 0, 2 * Math.PI);
    ctx.lineWidth = width / scale;
    ctx.setLineDash(dash ? [dash / scale, dash / scale] : []);
    ctx.strokeStyle = color;
    ctx.stroke();
    ctx.setLineDash([]);
  };
  const around = r + 3 / scale;
  ctx.save();
  if (maybe && !bad && !missed) {
    // one link away, not read: a dashed ring set clear of the mark, on a solid underlay in the canvas background, so the
    // dashes stay dashes against a bright type ring in either theme (and at a small zoom) instead of blurring into one
    const out = r + 5.5 / scale;
    ring(out, 3.5, withAlpha(c.background, Math.max(alpha, 0.6)));
    ring(out, 1.6, withAlpha(c.text, 0.9 * Math.max(alpha, 0.6)), 3);
  }
  if (bad) ring(around, 2.2, c.warn, 3);
  else if (missed) ring(around, 2.2, c.ring, 3);
  if (role === "seen") ring(around, 1.4, withAlpha(c.muted, 0.95));
  else if (role === "read" || role === "cited") {
    const color = role === "cited" ? c.ring : c.text;
    ctx.beginPath();
    ctx.arc(x, y, around, 0, 2 * Math.PI);
    ctx.fillStyle = withAlpha(color, 0.22);
    ctx.fill();
    ring(around, role === "cited" ? 2.2 : 1.6, color);
  }
  if (d.view.current.has(id)) ring(r + 7 / scale, 2, withAlpha(c.ring, 0.95));
  ctx.restore();
}

/** The link between consecutive read pages, drawn under the nodes whether or not the graph has that edge. */
export function drawReplayPath(ctx: CanvasRenderingContext2D, nodes: readonly { id: string; x?: number; y?: number }[], path: readonly (readonly [string, string])[], scale: number, c: CanvasColors): void {
  const at = new Map(nodes.map((n) => [n.id, n] as const));
  ctx.save();
  ctx.lineWidth = 3 / scale;
  ctx.lineCap = "round";
  ctx.strokeStyle = withAlpha(c.ring, 0.85);
  for (const [a, b] of path) {
    const p = at.get(a);
    const q = at.get(b);
    if (p?.x == null || p.y == null || q?.x == null || q.y == null) continue;
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.lineTo(q.x, q.y);
    ctx.stroke();
  }
  ctx.restore();
}
