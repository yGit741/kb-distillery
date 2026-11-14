import type { EmbeddingReport } from "@/api/types";
import type { NeighborMap } from "../graphData";

/** The three views built on the embedding (flag ui.embedding-views): colour by topic, the meaning map, missing links. */
export type EmbedView = "topics" | "map" | "missing";
export const EMBED_VIEWS: readonly EmbedView[] = ["topics", "map", "missing"];

export type Point = EmbeddingReport["points"][number];
export type Pair = EmbeddingReport["near"][number];
export type Orphan = EmbeddingReport["isolated"][number];

/** A topic's name: the LLM name while it is current, else its number. */
export const topicName = (c: { id: number; name?: string | null }): string => c.name || `Topic ${c.id + 1}`;

/** Each page's topic (embedding cluster) and each topic's name. */
export function topicIndex(r: Pick<EmbeddingReport, "points" | "clusters">): { of: Map<string, number>; names: Map<number, string> } {
  return {
    of: new Map(r.points.map((p) => [p.slug, p.cluster])),
    names: new Map(r.clusters.map((c) => [c.id, topicName(c)])),
  };
}

/** Each page's position along the principal components, 0..1 per component. */
export function componentsOf(points: readonly Point[]): Map<string, readonly number[]> {
  return new Map(points.map((p) => [p.slug, p.pc.length ? p.pc : [p.x, p.y]]));
}

/** How many components a map axis may pick from. */
export const axisCount = (r: Pick<EmbeddingReport, "points" | "components">): number =>
  Math.max(2, Math.min(r.components.length || 2, r.points[0]?.pc.length || 2));

/** An axis as "low -> high" from the component's pole names; its number when unnamed. */
export function axisLabel(r: Pick<EmbeddingReport, "components">, i: number): string {
  const c = r.components.find((x) => x.index === i);
  return c?.low_name && c.high_name ? `${c.low_name} → ${c.high_name}` : `Component ${i + 1}`;
}

/**
 * The meaning map: each page at (pc[x], pc[y]) stretched over the drawn pages' range to a square of side 2 * half,
 * high values up; pages without a vector stand in a short column to the right of it, in id order, so the map itself
 * holds only measured positions.
 */
export function meaningPositions(
  ids: readonly string[],
  pc: ReadonlyMap<string, readonly number[]>,
  axes: readonly [number, number],
  half: number,
): Map<string, readonly [number, number]> {
  const out = new Map<string, readonly [number, number]>();
  const at: [string, number, number][] = [];
  const rest: string[] = [];
  for (const id of ids) {
    const v = pc.get(id);
    const x = v?.[axes[0]];
    const y = v?.[axes[1]];
    if (x === undefined || y === undefined) rest.push(id);
    else at.push([id, x, y]);
  }
  const span = (k: 1 | 2) => {
    let lo = Infinity;
    let hi = -Infinity;
    for (const a of at) {
      lo = Math.min(lo, a[k]);
      hi = Math.max(hi, a[k]);
    }
    const d = hi - lo;
    return (v: number) => (d > 0 ? (v - lo) / d : 0.5);
  };
  const sx = span(1);
  const sy = span(2);
  for (const [id, x, y] of at) out.set(id, [(sx(x) - 0.5) * 2 * half, (0.5 - sy(y)) * 2 * half]);
  rest.sort((a, b) => a.localeCompare(b));
  const step = rest.length > 1 ? Math.min((2 * half) / (rest.length - 1), 30) : 0;
  const top = (-step * (rest.length - 1)) / 2;
  rest.forEach((id, i) => out.set(id, [half * 1.25, top + i * step]));
  return out;
}

/** Whether two pages are linked either way. */
export const linked = (neighbors: NeighborMap, a: string, b: string): boolean =>
  !!neighbors.get(a)?.includes(b) || !!neighbors.get(b)?.includes(a);

/**
 * Missing links: pairs close in meaning (the server's `near`, closest first) whose pages both exist in the graph and
 * are not linked either way.
 */
export function missingPairs(near: readonly Pair[], known: ReadonlySet<string>, neighbors: NeighborMap): Pair[] {
  return near.filter((p) => p.a.slug !== p.b.slug && known.has(p.a.slug) && known.has(p.b.slug) && !linked(neighbors, p.a.slug, p.b.slug));
}

/** Semantic orphans that are pages of the graph, the furthest from any other first. */
export const orphansIn = (isolated: readonly Orphan[], known: ReadonlySet<string>): Orphan[] =>
  isolated.filter((o) => known.has(o.slug)).sort((a, b) => a.nearest - b.nearest);

/** The median of the nearest-neighbour cosines and of the pair cosines, from the server's percentiles. */
export function closeness(s: EmbeddingReport["similarity"] | null | undefined): { pairs: number; low: number; high: number; nearest: number } | null {
  if (!s) return null;
  const p = s.percentiles;
  const n = s.nearest_percentiles;
  const pairs = p.p50;
  const nearest = n.p50;
  if (pairs === undefined || nearest === undefined) return null;
  // "most pairs" = the middle half
  return { pairs, low: p.p25 ?? pairs, high: p.p75 ?? pairs, nearest };
}
