import type { SearchHit } from "@/api";
import { withNeighbors, type NeighborMap } from "./graphData";
import type { GNode } from "./types";

/** Title/slug match score for the Space search; 0 = no match. */
export function scorePage(n: GNode, q: string): number {
  const t = (n.title || "").toLowerCase();
  const s = n.id.toLowerCase();
  if (!q) return 0;
  if (t === q) return 100;
  if (t.startsWith(q)) return 80;
  if (t.includes(` ${q}`)) return 62;
  if (t.includes(q)) return 50;
  if (s.includes(q.replace(/\s+/g, "-"))) return 40;
  const terms = q.split(/\s+/);
  return terms.length > 1 && terms.every((x) => t.includes(x) || s.includes(x)) ? 30 : 0;
}

/** The best title/slug matches (link count breaks ties), at most `limit`. */
export function findPages(nodes: readonly GNode[], raw: string, limit = 7): GNode[] {
  const q = raw.trim().toLowerCase();
  if (!q) return [];
  return nodes
    .map((n) => [scorePage(n, q) + Math.min(n.inDegree || 0, 20) / 10, n] as const)
    .filter(([s]) => s >= 30)
    .sort((a, b) => b[0] - a[0])
    .slice(0, limit)
    .map(([, n]) => n);
}

/** Full-text hits that are not already a title match and are pages of this graph. */
export function textHits(hits: readonly SearchHit[], byId: ReadonlyMap<string, GNode>, skip: readonly GNode[], limit = 6) {
  const seen = new Set(skip.map((n) => n.id));
  return hits.filter((h) => !seen.has(h.id) && byId.has(h.id)).slice(0, limit);
}

export type ViewKind = "search" | "picked" | "scope";

/** A set of pages plus their neighbours, drawn past every other filter. */
export interface GraphView {
  kind: ViewKind;
  /** What it was made from: the query, or the scope slug. */
  label: string;
  /** The pages asked for. */
  hits: ReadonlySet<string>;
  /** hits + neighbours: what is drawn. */
  shown: ReadonlySet<string>;
}

export function makeView(
  kind: ViewKind,
  label: string,
  ids: Iterable<string>,
  known: ReadonlyMap<string, GNode>,
  neighbors: NeighborMap,
): GraphView | null {
  const hits = new Set([...ids].filter((id) => known.has(id)));
  if (!hits.size) return null;
  return { kind, label, hits, shown: withNeighbors(hits, neighbors) };
}

/** Picking more pages extends a picked view instead of replacing it. */
export function extendView(prev: GraphView | null, next: GraphView | null): GraphView | null {
  if (!next || !prev || prev.kind !== "picked" || next.kind !== "picked") return next;
  return { ...next, hits: new Set([...prev.hits, ...next.hits]), shown: new Set([...prev.shown, ...next.shown]) };
}

export const parsePages = (raw?: string): string[] =>
  (raw ?? "").split(",").map((s) => s.trim()).filter(Boolean);

/** A scope's projection lists: the scope page, the pages it covers (hop0) and their neighbours (hop1). */
export function scopeIds(slug: string, projection: { hop0?: unknown[]; hop1?: unknown[] } | undefined): string[] {
  const strs = (a?: unknown[]) => (a ?? []).filter((x): x is string => typeof x === "string");
  return [slug, ...strs(projection?.hop0), ...strs(projection?.hop1)];
}
