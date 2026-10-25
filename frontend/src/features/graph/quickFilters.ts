import type { NeighborMap } from "./graphData";
import type { GNode } from "./types";

/**
 * The legend's one-click filters, applied after the type, rule and colour-key filters on the pages left. Each is
 * off at 0 (or null); each keeps a page only if it passes. They run in this order, so later ones see what the
 * earlier left: Recent (added in the last N days), Connected (at least N links among the pages shown), Backbone
 * (the k-core of what is shown), then Neighbours (within N hops of the selection) or Path (the shortest chains
 * between two selected pages). Selected pages always stay.
 */
export interface QuickFilters {
  /** days; 0 = off */
  recent: number;
  /** minimum links among the pages shown; 0 = off */
  connected: number;
  /** k of the k-core; 0 = off */
  backbone: number;
  /** hops from the selection; 0 = off */
  neighbours: number;
  /** keep only the shortest paths between the two selected pages */
  path: boolean;
}

export const QUICK_OFF: QuickFilters = { recent: 0, connected: 0, backbone: 0, neighbours: 0, path: false };
/** The value a chip switches on with, and the range its stepper walks. */
export const QUICK_STEPS = {
  recent: [1, 3, 7, 14, 30, 60, 90, 180],
  connected: [1, 2, 3, 5],
  backbone: [2, 3, 4, 5, 6],
  neighbours: [1, 2, 3],
} as const;

const DAY = 86_400_000;

/** Neighbours of each kept page among the kept pages. */
function within(keep: ReadonlySet<string>, nb: NeighborMap): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const id of keep) out.set(id, [...new Set(nb.get(id) ?? [])].filter((j) => j !== id && keep.has(j)));
  return out;
}

/** Breadth-first distances from `from` over `adj`, up to `max` hops. */
function distances(from: Iterable<string>, adj: ReadonlyMap<string, readonly string[]>, max = Infinity): Map<string, number> {
  const d = new Map<string, number>();
  let frontier = [...from].filter((id) => adj.has(id));
  frontier.forEach((id) => d.set(id, 0));
  for (let k = 1; frontier.length && k <= max; k++) {
    const next: string[] = [];
    for (const id of frontier) for (const j of adj.get(id) ?? []) if (!d.has(j)) (d.set(j, k), next.push(j));
    frontier = next;
  }
  return d;
}

/** The k-core: repeatedly drop pages with fewer than k links to the pages still kept. */
export function kCore(keep: ReadonlySet<string>, nb: NeighborMap, k: number): Set<string> {
  const adj = within(keep, nb);
  const deg = new Map([...adj].map(([id, ns]) => [id, ns.length]));
  const out = new Set(keep);
  const queue = [...out].filter((id) => (deg.get(id) ?? 0) < k);
  while (queue.length) {
    const id = queue.pop()!;
    if (!out.delete(id)) continue;
    for (const j of adj.get(id) ?? []) {
      if (!out.has(j)) continue;
      const dj = (deg.get(j) ?? 0) - 1;
      deg.set(j, dj);
      if (dj < k) queue.push(j);
    }
  }
  return out;
}

/** Every page on some shortest path between a and b (within the pages kept); empty when they do not meet. */
export function shortestPaths(keep: ReadonlySet<string>, nb: NeighborMap, a: string, b: string): Set<string> {
  const adj = within(keep, nb);
  const da = distances([a], adj);
  const db = distances([b], adj);
  const d = da.get(b);
  if (d === undefined) return new Set();
  return new Set([...da].filter(([id, x]) => x + (db.get(id) ?? Infinity) === d).map(([id]) => id));
}

export function applyQuick(
  visible: ReadonlySet<string>,
  byId: ReadonlyMap<string, GNode>,
  nb: NeighborMap,
  selection: ReadonlySet<string>,
  q: QuickFilters,
  now = Date.now(),
): Set<string> {
  let keep = new Set(visible);
  const sel = [...selection].filter((id) => visible.has(id));
  const pin = (s: Set<string>) => (sel.forEach((id) => s.add(id)), s);
  if (q.recent > 0) {
    const since = now - q.recent * DAY;
    keep = pin(new Set([...keep].filter((id) => Date.parse(byId.get(id)?.added || "") >= since)));
  }
  if (q.connected > 0) {
    const adj = within(keep, nb);
    keep = pin(new Set([...keep].filter((id) => (adj.get(id)?.length ?? 0) >= q.connected)));
  }
  if (q.backbone > 0) keep = pin(kCore(keep, nb, q.backbone));
  if (q.path && sel.length === 2) keep = pin(shortestPaths(keep, nb, sel[0]!, sel[1]!));
  else if (q.neighbours > 0 && sel.length) keep = new Set(distances(sel, within(keep, nb), q.neighbours).keys());
  return keep;
}
