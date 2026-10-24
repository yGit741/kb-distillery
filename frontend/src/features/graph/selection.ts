import type { PathResult } from "@/api";
import { buildNeighborMap, sourcesOf, type NeighborMap } from "./graphData";
import type { GLink, GNode } from "./types";

export interface Pt {
  x: number;
  y: number;
}

/** A right-drag region in viewport pixels: a rectangle (two corners) or a freeform lasso. */
export type Region = { kind: "box"; a: Pt; b: Pt } | { kind: "lasso"; pts: readonly Pt[] };

/** Drags shorter than this are a plain right-click (the page menu), not a selection. */
export const DRAG_PX = 4;
/** A lasso with fewer points than this is an accident. */
export const MIN_LASSO_POINTS = 4;

export const boxContains = (a: Pt, b: Pt, p: Pt): boolean =>
  p.x >= Math.min(a.x, b.x) && p.x <= Math.max(a.x, b.x) && p.y >= Math.min(a.y, b.y) && p.y <= Math.max(a.y, b.y);

/** Even-odd ray casting. */
export function polyContains(poly: readonly Pt[], p: Pt): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i] as Pt;
    const b = poly[j] as Pt;
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

export const regionContains = (r: Region, p: Pt): boolean => (r.kind === "box" ? boxContains(r.a, r.b, p) : polyContains(r.pts, p));

/** The ids whose screen position lies inside the region (a node with no position yet is skipped). */
export function pickInRegion(r: Region, ids: Iterable<string>, screenOf: (id: string) => Pt | null): string[] {
  const out: string[] = [];
  for (const id of ids) {
    const p = screenOf(id);
    if (p && Number.isFinite(p.x) && Number.isFinite(p.y) && regionContains(r, p)) out.push(id);
  }
  return out;
}

/** Links between drawn pages only: expanding a selection follows what is on the canvas. */
export function visibleAdjacency(links: readonly Pick<GLink, "source" | "target">[], visible: ReadonlySet<string>): NeighborMap {
  return buildNeighborMap(links.filter((l) => visible.has(l.source) && visible.has(l.target)));
}

/** Everything one hop from `ids` that is not in `ids`; `keep` narrows it (sources only, a type...). */
export function neighboursOf(ids: Iterable<string>, adj: NeighborMap, keep?: (id: string) => boolean): string[] {
  const from = new Set(ids);
  const out = new Set<string>();
  for (const id of from) for (const n of adj.get(id) ?? []) if (!from.has(n) && (!keep || keep(n))) out.add(n);
  return [...out];
}

/** Source pages under the non-source members of the selection (a collection's members, a concept's sources). */
export function memberSources(ids: Iterable<string>, neighbors: NeighborMap, byId: ReadonlyMap<string, GNode>): string[] {
  const from = new Set(ids);
  const out = new Set<string>();
  for (const id of from) {
    if (byId.get(id)?.layer === "source") continue;
    for (const s of sourcesOf(id, neighbors, byId)) if (!from.has(s)) out.add(s);
  }
  return [...out];
}

/** Papers that cite, or are cited by, the selection (and exist as pages). */
export function citationNeighbours(
  ids: ReadonlySet<string>,
  links: readonly { source: string; target: string }[],
  known: ReadonlySet<string>,
): string[] {
  const out = new Set<string>();
  for (const l of links) {
    if (ids.has(l.source) && known.has(l.target) && !ids.has(l.target)) out.add(l.target);
    if (ids.has(l.target) && known.has(l.source) && !ids.has(l.source)) out.add(l.source);
  }
  return [...out];
}

/** The shortest route of a path answer (ids in order), or [] when the pages are not connected. */
export const routeOf = (res: PathResult): string[] => res.paths[0]?.nodes ?? [];

export const typesOf = (ids: Iterable<string>, byId: ReadonlyMap<string, GNode>): string[] => {
  const t = new Set<string>();
  for (const id of ids) {
    const type = byId.get(id)?.type;
    if (type) t.add(type);
  }
  return [...t].sort();
};

export const onlyType = (ids: Iterable<string>, byId: ReadonlyMap<string, GNode>, type: string): string[] =>
  [...ids].filter((id) => byId.get(id)?.type === type);

/** Selected ids that are pages (never a raw pile). */
export const pageIds = (ids: Iterable<string>, byId: ReadonlyMap<string, GNode>): string[] => [...ids].filter((id) => byId.has(id));
