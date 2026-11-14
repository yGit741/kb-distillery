import type { GraphNode, GraphSnapshot } from "@/api";

type GraphKb = NonNullable<GraphSnapshot["kbs"]>[number];
import { parseRawLayer } from "./rawLayer";

/** A node as the API returns it (layer, type, depth, areas, degrees, preview, properties). */
export type GNode = GraphNode;

/** A link between two page ids. `shared` links are drawn between concepts that share sources; `cites` (a paper
 * cites a paper) only in a view that draws that relation (./lab/views `edges`), always with its arrow. */
export interface GLink {
  source: string;
  target: string;
  kind: "wikilink" | "related" | "book" | "shared" | "cites" | "pile-page" | "pile-pile";
  shared?: number;
  /** pile links: source files behind the edge */
  count?: number;
}

/** One raw file of the data layer (a corpus row as the graph API reports it). */
export interface RawNode {
  id: string;
  path: string;
  format: string;
  ext: string;
  disposition: string;
  companion_of: string | null;
  collection: string[];
  slug: string | null;
  year: number | null;
  title: string;
}

/** A raw file that feeds a page (`raw:<path>` -> slug). */
export interface RawLink {
  source: string;
  target: string;
  kind: string;
}

/** The data layer: one pile per raw format, its edges to pages and to other piles, and the file rows. */
export interface RawLayer {
  piles: GNode[];
  links: GLink[];
  nodes: RawNode[];
  rawLinks: RawLink[];
}

export interface Positioned {
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

/** What force-graph holds: the API node plus the coordinates the simulation writes into it. */
export type SimNode = GNode & Positioned;
export type SimLink = Omit<GLink, "source" | "target"> & { source: string | SimNode; target: string | SimNode };

export interface BookInfo {
  done: number;
  content: number;
  total: number;
  parts: { title: string; start: number; end: number; status: string; slug: string }[];
}

export interface PartInfo {
  book: string;
  pages: string;
  section: string;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;

export function bookOf(n: GNode): BookInfo | null {
  const b = n["book"];
  if (!isObj(b) || !Array.isArray(b["parts"])) return null;
  const parts = (b["parts"] as unknown[]).filter(isObj).map((p) => ({
    title: String(p["title"] ?? ""),
    start: Number(p["start"] ?? 0),
    end: Number(p["end"] ?? 0),
    status: String(p["status"] ?? ""),
    slug: String(p["slug"] ?? ""),
  }));
  return { done: Number(b["done"] ?? 0), content: Number(b["content"] ?? 0), total: Number(b["total"] ?? 0), parts };
}

export function partOf(n: GNode): PartInfo | null {
  const p = n["part"];
  if (!isObj(p)) return null;
  return { book: String(p["book"] ?? ""), pages: String(p["pages"] ?? ""), section: String(p["section"] ?? "") };
}

export interface ConceptLink {
  source: string;
  target: string;
  shared: number;
}

/** The slice of a snapshot the pure modules need. */
export interface GraphModel {
  nodes: readonly GNode[];
  links: readonly GLink[];
  conceptLinks: readonly ConceptLink[];
  /** The knowledge bases on the canvas (several: ids are `<kb>:<slug>` and the regions are the knowledge bases). */
  kbs?: readonly GraphKb[];
  /** Present while the data layer is loaded (`?raw=1`). Piles are drawn but are not pages: never in `nodes`. */
  raw?: RawLayer;
  /** Typed relations (flag `graph-relations`): present only when the snapshot carries them. Drawn only by a view
   * that names their kind (./storyEdges). */
  relations?: readonly GRelation[];
}

/** A typed relation between two page ids: stated on a page (`stored`) or derived from vault data (`computed`). */
export interface GRelation {
  source: string;
  target: string;
  kind: string;
  origin: string;
  note: string;
}

export function toModel(snap: GraphSnapshot): GraphModel {
  const raw = parseRawLayer(snap);
  return {
    ...(raw ? { raw } : {}),
    ...(snap.relations
      ? { relations: snap.relations.map((r) => ({ source: r.source, target: r.target, kind: r.kind, origin: r.origin, note: r.note ?? "" })) }
      : {}),
    nodes: snap.nodes,
    kbs: snap.kbs ?? [],
    links: snap.links.map((l) => ({
      source: l.source,
      target: l.target,
      kind: l.kind === "related" || l.kind === "book" ? l.kind : "wikilink",
    })),
    conceptLinks: snap.concept_links.map((c) => ({ source: c.source, target: c.target, shared: c.shared })),
  };
}

export const degreeOf = (n: GNode): number => (n.inDegree || 0) + (n.outDegree || 0);
