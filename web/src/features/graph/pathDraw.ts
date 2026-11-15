import { withAlpha, type CanvasColors } from "./canvasTheme";
import type { SimLink, SimNode } from "./types";

/**
 * A shortest path on the canvas (flag graph-algos). The path's links are drawn bold over the graph; while the line is
 * previewed, a page on the path that the current view hides (a source in the Concepts view) is brought in as a ghost:
 * pinned between its neighbours on the path, faded, with a dashed outline, and with no links but the path's own.
 */

export type PathLinks = readonly (readonly [string, string])[];

/** The unordered key of a link between two pages. */
export const pairKey = (a: string, b: string) => (a < b ? `${a}\0${b}` : `${b}\0${a}`);

/** The pages on the path the view does not draw, in path order. */
export function pathGhosts(links: PathLinks, drawn: ReadonlySet<string>): string[] {
  const out = new Set<string>();
  for (const [a, b] of links) for (const id of [a, b]) if (!drawn.has(id)) out.add(id);
  return [...out];
}

interface Pos {
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

/**
 * Seeds each ghost at the middle of its neighbours on the path that have a place (ghosts next to ghosts are placed in
 * turn, so a run of hidden pages spreads along the line between its drawn ends) and pins it there, so bringing the
 * page in barely moves what is drawn. A ghost with no placed page anywhere along the path (the whole path hidden)
 * goes in a short row from `origin`. Returns the ids it pinned.
 */
export function seedGhosts(prev: Map<string, Pos>, ghosts: readonly string[], links: PathLinks, origin = { x: 0, y: 0 }): string[] {
  const nb = new Map<string, string[]>();
  for (const [a, b] of links) {
    nb.set(a, [...(nb.get(a) ?? []), b]);
    nb.set(b, [...(nb.get(b) ?? []), a]);
  }
  const left = ghosts.filter((id) => prev.get(id)?.x == null);
  const pinned: string[] = [];
  for (let round = 0; left.length && round < ghosts.length + 1; round++) {
    for (let i = left.length - 1; i >= 0; i--) {
      const id = left[i]!;
      const placed = (nb.get(id) ?? []).map((o) => prev.get(o)).filter((p): p is Pos & { x: number; y: number } => p?.x != null && p.y != null);
      if (!placed.length) continue;
      // a page with one placed neighbour sits a little off it, not on top of it
      const x = placed.reduce((s, p) => s + p.x, 0) / placed.length + (placed.length === 1 ? 40 : 0);
      const y = placed.reduce((s, p) => s + p.y, 0) / placed.length + (placed.length === 1 ? 24 : 0);
      prev.set(id, { x, y, fx: x, fy: y });
      pinned.push(id);
      left.splice(i, 1);
    }
  }
  left.forEach((id, i) => {
    const x = origin.x + (i - (left.length - 1) / 2) * 60;
    prev.set(id, { x, y: origin.y, fx: x, fy: origin.y });
    pinned.push(id);
  });
  return pinned;
}

/** The links of the drawn data that lie on the path, in path order (a link the data lacks is left out). */
export function pathSimLinks(links: readonly SimLink[], path: PathLinks): SimLink[] {
  const end = (e: string | SimNode) => (typeof e === "string" ? e : e.id);
  const byKey = new Map<string, SimLink>();
  for (const l of links) {
    const k = pairKey(end(l.source), end(l.target));
    if (!byKey.has(k)) byKey.set(k, l);
  }
  const out = new Set<SimLink>();
  for (const [a, b] of path) {
    const l = byKey.get(pairKey(a, b));
    if (l) out.add(l);
  }
  return [...out];
}

/** A ghost's dashed outline, just outside its dot. */
export function drawGhostRing(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, scale: number, colors: CanvasColors): void {
  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, r + 3 / scale, 0, Math.PI * 2);
  ctx.setLineDash([3 / scale, 2.5 / scale]);
  ctx.strokeStyle = withAlpha(colors.text, 0.7);
  ctx.lineWidth = 1.2 / scale;
  ctx.stroke();
  ctx.restore();
}

/** How faded a ghost's dot is drawn. */
export const GHOST_ALPHA = 0.45;
/** A path link's width in screen pixels (a lit edge is 1.5). */
export const PATH_WIDTH = 3;
