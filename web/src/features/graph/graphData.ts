import type { GLink, GNode, GraphModel, Positioned, SimLink, SimNode } from "./types";

export type NeighborMap = ReadonlyMap<string, readonly string[]>;

/** Undirected adjacency over all links (hidden pages included: a neighbour list does not depend on the filters). */
export function buildNeighborMap(links: readonly Pick<GLink, "source" | "target">[]): NeighborMap {
  const sets = new Map<string, Set<string>>();
  const add = (a: string, b: string) => {
    let s = sets.get(a);
    if (!s) sets.set(a, (s = new Set()));
    s.add(b);
  };
  for (const l of links) {
    add(l.source, l.target);
    add(l.target, l.source);
  }
  const out = new Map<string, string[]>();
  sets.forEach((s, k) => out.set(k, [...s]));
  return out;
}

/** The source pages behind a page: its source-layer neighbours (for a collection, its members). */
export function sourcesOf(id: string, neighbors: NeighborMap, byId: ReadonlyMap<string, GNode>): string[] {
  return (neighbors.get(id) ?? []).filter((n) => byId.get(n)?.layer === "source");
}

/** True when any source page is drawn, whether by a type chip or by "See sources". */
export function sourcesDrawn(visible: ReadonlySet<string>, byId: ReadonlyMap<string, GNode>): boolean {
  for (const id of visible) if (byId.get(id)?.layer === "source") return true;
  return false;
}

/**
 * Concepts that share sources get a thin dashed edge labelled with the count, so hiding the source
 * layer keeps the structure it carried (graph `concept_links`). Skipped for a pair already linked.
 */
export function sharedSourceLinks(
  conceptLinks: GraphModel["conceptLinks"],
  drawn: ReadonlySet<string>,
  linked: ReadonlySet<string>,
): GLink[] {
  const out: GLink[] = [];
  for (const c of conceptLinks) {
    if (!drawn.has(c.source) || !drawn.has(c.target)) continue;
    if (linked.has(`${c.source}|${c.target}`) || linked.has(`${c.target}|${c.source}`)) continue;
    out.push({ source: c.source, target: c.target, kind: "shared", shared: c.shared });
  }
  return out;
}

/** Shared-source edges are hidden until their meaning is specified better; flip to draw them again. */
export const SHOW_SHARED_EDGES = false;

export interface GraphData {
  nodes: SimNode[];
  links: SimLink[];
}

/**
 * The nodes and links force-graph draws: the visible pages, the links among them, and the shared-source
 * edges while no source page is drawn. Positions of nodes that stay are carried over so a filter change
 * does not scramble the layout.
 */
export function buildGraphData(
  model: GraphModel,
  visible: ReadonlySet<string>,
  prev?: ReadonlyMap<string, Positioned>,
  shared = SHOW_SHARED_EDGES,
): GraphData {
  const byId = new Map(model.nodes.map((n) => [n.id, n] as const));
  const nodes: SimNode[] = [];
  const place = (n: GNode): SimNode => {
    const p = prev?.get(n.id);
    const node: SimNode = { ...n };
    if (p && p.x != null && p.y != null) {
      node.x = p.x;
      node.y = p.y;
      if (p.fx != null) node.fx = p.fx;
      if (p.fy != null) node.fy = p.fy;
    }
    return node;
  };
  for (const n of model.nodes) if (visible.has(n.id)) nodes.push(place(n));
  // the data layer: piles are always drawn, tied to the pages they feed that are drawn too
  const pileIds = new Set<string>();
  for (const p of model.raw?.piles ?? []) {
    pileIds.add(p.id);
    nodes.push(place(p));
  }
  const links: GLink[] = model.links.filter((l) => visible.has(l.source) && visible.has(l.target));
  if (shared && !sourcesDrawn(visible, byId)) {
    const linked = new Set(links.map((l) => `${l.source}|${l.target}`));
    links.push(...sharedSourceLinks(model.conceptLinks, visible, linked));
  }
  for (const l of model.raw?.links ?? []) {
    if (pileIds.has(l.source) && (pileIds.has(l.target) || visible.has(l.target))) links.push(l);
  }
  return { nodes, links: links.map((l) => ({ ...l })) };
}

/**
 * How strongly two pages are tied, keyed "a\0b" with a < b: one per wikilink, related or book link in either
 * direction, plus the shared-source count of a concept link. Orders a clicked page's neighbours stably.
 */
export function edgeWeights(model: Pick<GraphModel, "links" | "conceptLinks">): ReadonlyMap<string, number> {
  const out = new Map<string, number>();
  const add = (a: string, b: string, w: number) => {
    const k = a < b ? `${a}\0${b}` : `${b}\0${a}`;
    out.set(k, (out.get(k) ?? 0) + w);
  };
  for (const l of model.links) if (l.kind === "wikilink" || l.kind === "related" || l.kind === "book") add(l.source, l.target, 1);
  for (const c of model.conceptLinks) add(c.source, c.target, c.shared);
  return out;
}

export const edgeWeight = (w: ReadonlyMap<string, number>, a: string, b: string): number => w.get(a < b ? `${a}\0${b}` : `${b}\0${a}`) ?? 0;

/** Pages reached from `ids` in one step, together with `ids` themselves (the "+ neighbours" of a view). */
export function withNeighbors(ids: Iterable<string>, neighbors: NeighborMap): Set<string> {
  const out = new Set<string>();
  for (const id of ids) {
    out.add(id);
    for (const n of neighbors.get(id) ?? []) out.add(n);
  }
  return out;
}

/** Largest connected component among `visible` (the part fit-to-view frames; stray islands drift far out). */
export function largestComponent(visible: ReadonlySet<string>, neighbors: NeighborMap): Set<string> {
  const seen = new Set<string>();
  let best = new Set<string>();
  for (const start of visible) {
    if (seen.has(start)) continue;
    const comp = new Set([start]);
    const stack = [start];
    seen.add(start);
    while (stack.length) {
      for (const nb of neighbors.get(stack.pop() as string) ?? []) {
        if (seen.has(nb) || !visible.has(nb)) continue;
        seen.add(nb);
        comp.add(nb);
        stack.push(nb);
      }
    }
    if (comp.size > best.size) best = comp;
  }
  return best;
}

/** Same members, whatever the Set objects (a new Set with the same pages is not a change of the drawn set). */
export function sameSet<T>(a: ReadonlySet<T>, b: ReadonlySet<T>): boolean {
  if (a === b) return true;
  if (a.size !== b.size) return false;
  for (const x of a) if (!b.has(x)) return false;
  return true;
}
