/** The magnetic pointer: the hovered page is the nearest one, not only the one under the pointer. */

export interface ScreenNode {
  id: string;
  x: number;
  y: number;
  /** Radius in screen pixels. */
  r: number;
}

export const REACH_MIN = 12;
export const REACH_MAX = 90;
export const REACH_SHARE = 0.6;
/** A current target is kept until another is this much closer, so a dense area does not flicker. */
export const STICKY = 1.2;

const rim = (n: ScreenNode, px: number, py: number) => Math.hypot(n.x - px, n.y - py) - n.r;

/** Rim-to-rim gap from `n` to its closest neighbour, screen px. */
export function gapOf(n: ScreenNode, all: readonly ScreenNode[]): number {
  let best = Infinity;
  for (const o of all) {
    if (o === n) continue;
    const d = Math.hypot(o.x - n.x, o.y - n.y) - n.r - o.r;
    if (d < best) best = d;
  }
  return Number.isFinite(best) ? Math.max(0, best) : 40;
}

/** How far a node's pull reaches: follows the spacing around it (density and zoom both count). */
export const reachOf = (n: ScreenNode, all: readonly ScreenNode[]): number =>
  Math.min(REACH_MAX, Math.max(REACH_MIN, gapOf(n, all) * REACH_SHARE));

/** Nearest node to the pointer within its own reach, or null (a miss). `current` is sticky. */
export function pickMagnetic(
  nodes: readonly ScreenNode[],
  px: number,
  py: number,
  current: string | null = null,
): string | null {
  let best: ScreenNode | null = null;
  let bd = Infinity;
  for (const n of nodes) {
    const d = rim(n, px, py);
    if (d < bd) {
      bd = d;
      best = n;
    }
  }
  if (!best) return null;
  const cur = current ? nodes.find((n) => n.id === current) : undefined;
  if (cur && cur !== best) {
    const td = rim(cur, px, py);
    if (td <= reachOf(cur, nodes) && td < bd * STICKY + 3) return cur.id;
  }
  return bd <= reachOf(best, nodes) ? best.id : null;
}
