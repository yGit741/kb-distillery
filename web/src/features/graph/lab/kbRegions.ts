import { withAlpha } from "../canvasTheme";
import type { SimNode } from "../types";
import { traceRoundedHull } from "./draw";
import { convexHull } from "./regions";

/**
 * Several knowledge bases on one canvas: each is one region, held together by a pull toward its own anchor (so a
 * page with no links cannot drift off), outlined with a dashed line (no tint: colour stays the page type) and
 * named above its top edge, where the name never covers a node. Dragging the name moves the whole region.
 */

/** Padding of the outline around the outermost nodes, in graph units. */
export const KB_PAD = 36;

export function kbGroups(nodes: readonly SimNode[]): Map<string, SimNode[]> {
  const out = new Map<string, SimNode[]>();
  for (const n of nodes) {
    if (!n.kb || n.x == null || n.y == null || !Number.isFinite(n.x) || !Number.isFinite(n.y)) continue;
    const g = out.get(n.kb);
    if (g) g.push(n);
    else out.set(n.kb, [n]);
  }
  return out;
}

/** Anchors in a row, left to right in `ids` order, spaced by the regions' expected sizes. */
export function kbAnchors(ids: readonly string[], counts: ReadonlyMap<string, number>, linkDistance: number): Map<string, [number, number]> {
  const radius = (id: string) => Math.sqrt(Math.max(1, counts.get(id) ?? 1)) * linkDistance * 0.55 + KB_PAD;
  const widths = ids.map((id) => 2 * radius(id));
  const gap = linkDistance * 2;
  const total = widths.reduce((a, b) => a + b, 0) + gap * Math.max(0, ids.length - 1);
  const out = new Map<string, [number, number]>();
  let x = -total / 2;
  ids.forEach((id, i) => {
    out.set(id, [x + widths[i]! / 2, 0]);
    x += widths[i]! + gap;
  });
  return out;
}

/** The dashed outline of every knowledge base's region (all its nodes inside). */
export function drawKbOutlines(ctx: CanvasRenderingContext2D, groups: ReadonlyMap<string, SimNode[]>, scale: number, color: string): void {
  ctx.save();
  ctx.setLineDash([6 / scale, 5 / scale]);
  ctx.lineWidth = 1.25 / scale;
  ctx.strokeStyle = withAlpha(color, 0.7);
  for (const list of groups.values()) {
    const hull = convexHull(list.map((n) => [n.x as number, n.y as number] as const));
    const pts = hull.length >= 3 ? hull : padPoints(list);
    if (traceRoundedHull(ctx, pts, KB_PAD)) ctx.stroke();
  }
  ctx.restore();
}

/** One or two nodes: a small box around them, so the region still has an outline. */
function padPoints(list: readonly SimNode[]): [number, number][] {
  const xs = list.map((n) => n.x as number);
  const ys = list.map((n) => n.y as number);
  const [x0, x1, y0, y1] = [Math.min(...xs) - 1, Math.max(...xs) + 1, Math.min(...ys) - 1, Math.max(...ys) + 1];
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
}

/** Where a region's name sits: centred over it, just above the top of its outline (graph units). */
export function kbLabelSpot(list: readonly SimNode[]): { x: number; top: number } {
  let x0 = Infinity, x1 = -Infinity, top = Infinity;
  for (const n of list) {
    x0 = Math.min(x0, n.x as number);
    x1 = Math.max(x1, n.x as number);
    top = Math.min(top, n.y as number);
  }
  return { x: (x0 + x1) / 2, top: top - KB_PAD };
}
