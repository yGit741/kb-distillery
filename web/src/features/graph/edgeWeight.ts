/**
 * How heavy a link is drawn, by how far in the view is. At the whole-graph fit hundreds of links overlap, so each
 * stays a quiet texture; up close a handful are left on screen and each one is a relation, so it is drawn as a line:
 * wider and more opaque, growing with the nodes (their radius follows the square root of the zoom too).
 */

/** 0 at the whole-graph fit (zoom about 0.7) and 1 once a handful of pages fill the screen (zoom about 5.5). */
export const zoomIn = (k: number): number => Math.max(0, Math.min(1, (Math.sqrt(k > 0 ? k : 1) - 0.85) / 1.5));

/** A link's width in screen px: a shared-sources link by how many it shares (up to 6), any other link one weight. */
export function edgeWidth(kind: string, shared: number | undefined, k: number): number {
  const rest = kind === "shared" ? 0.55 + Math.min(shared ?? 1, 6) * 0.13 : 0.95;
  return rest * (1 + 0.75 * zoomIn(k));
}

/** Flag calm-graph: the share of the usual opacity links rest at (a hovered page still lights its own). */
export const calmEdge = (k: number): number => 0.55 + 0.3 * zoomIn(k);
