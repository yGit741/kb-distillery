import { glyphOf, GLYPH_LABEL, type SourceGlyph } from "../encoding/spec";
import type { NeighborMap } from "../graphData";
import { pluralize } from "../shell/corners/typeGroups";
import type { GNode } from "../types";

/**
 * The Health view's numbers (flag knowledge-health), computed from the graph the screen already holds; nothing is
 * stored. A source kind is every source type that shares an icon (the page-types card groups them the same way).
 * Each source page is in exactly one state:
 * - waiting: still at `depth: listed` (cataloged, not read yet);
 * - unlinked: digested, but linked to no concept page;
 * - healthy: digested and linked to at least one concept page.
 */
export type SourceState = "waiting" | "unlinked" | "healthy";

export interface KindStat {
  /** the icon the kind's types share */
  kind: SourceGlyph;
  /** "Papers", "Lectures" */
  label: string;
  /** the first type of the kind, for its icon */
  type: string;
  total: number;
  waiting: number;
  unlinked: number;
  healthy: number;
}

type ById = ReadonlyMap<string, GNode>;

const conceptsOf = (id: string, neighbors: NeighborMap, byId: ById): string[] => [...new Set((neighbors.get(id) ?? []).filter((m) => byId.get(m)?.layer === "concept"))];

export function sourceState(n: GNode, neighbors: NeighborMap, byId: ById): SourceState {
  if ((n.depth || "listed") === "listed") return "waiting";
  return conceptsOf(n.id, neighbors, byId).length ? "healthy" : "unlinked";
}

/** One row per source kind, largest first. `waiting + unlinked + healthy` is `total`. */
export function sourceKinds(nodes: readonly GNode[], neighbors: NeighborMap, byId: ById): KindStat[] {
  const out = new Map<SourceGlyph, KindStat>();
  for (const n of nodes) {
    if (n.layer !== "source") continue;
    const kind = glyphOf(n.type);
    const k = out.get(kind) ?? { kind, label: pluralize(GLYPH_LABEL[kind]), type: n.type, total: 0, waiting: 0, unlinked: 0, healthy: 0 };
    k.total += 1;
    k[sourceState(n, neighbors, byId)] += 1;
    out.set(kind, k);
  }
  return [...out.values()].sort((a, b) => b.total - a.total || a.label.localeCompare(b.label));
}

/**
 * The concept pages a kind's digested sources link to: what the dial spotlights on the map, and the same concepts the
 * inside of the kind lists (a waiting source feeds nothing yet, whatever its stub links to).
 */
export function fedConcepts(kind: SourceGlyph, nodes: readonly GNode[], neighbors: NeighborMap, byId: ById): Set<string> {
  const out = new Set<string>();
  for (const n of nodes) {
    if (n.layer !== "source" || glyphOf(n.type) !== kind || sourceState(n, neighbors, byId) === "waiting") continue;
    for (const c of conceptsOf(n.id, neighbors, byId)) out.add(c);
  }
  return out;
}

export interface KindDetail {
  /** the kind's healthy sources, the ones feeding most concepts first */
  sources: { node: GNode; concepts: string[] }[];
  /** the concepts they feed, the least supported first, people after them; `support` counts sources of every kind */
  concepts: { node: GNode; support: number }[];
  waiting: GNode[];
  unlinked: GNode[];
}

const title = (n: GNode): string => n.title || n.id;
const byTitle = (a: GNode, b: GNode) => title(a).localeCompare(title(b));

/** Inside a kind: its sources beside the concepts they feed, and the sources that feed nothing yet. */
export function kindDetail(kind: SourceGlyph, nodes: readonly GNode[], neighbors: NeighborMap, byId: ById, support: ReadonlyMap<string, number>): KindDetail {
  const d: KindDetail = { sources: [], concepts: [], waiting: [], unlinked: [] };
  const fed = new Set<string>();
  for (const n of nodes) {
    if (n.layer !== "source" || glyphOf(n.type) !== kind) continue;
    const state = sourceState(n, neighbors, byId);
    if (state !== "healthy") {
      d[state].push(n);
      continue;
    }
    const concepts = conceptsOf(n.id, neighbors, byId);
    for (const c of concepts) fed.add(c);
    d.sources.push({ node: n, concepts });
  }
  d.sources.sort((a, b) => b.concepts.length - a.concepts.length || byTitle(a.node, b.node));
  const person = (n: GNode) => (n.type === "person" ? 1 : 0);
  d.concepts = [...fed]
    .map((id) => ({ node: byId.get(id)!, support: support.get(id) ?? 0 }))
    .sort((a, b) => person(a.node) - person(b.node) || a.support - b.support || byTitle(a.node, b.node));
  d.waiting.sort(byTitle);
  d.unlinked.sort(byTitle);
  return d;
}

/** "8 waiting, 3 feed no concept", or "all in use" when the kind has no open issue. */
export function kindLine(k: Pick<KindStat, "waiting" | "unlinked">): string {
  const parts = [k.waiting ? `${k.waiting} waiting` : "", k.unlinked ? `${k.unlinked} feed no concept` : ""].filter(Boolean);
  return parts.length ? parts.join(", ") : "all in use";
}
