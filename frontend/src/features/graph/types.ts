import type { GraphNode, GraphSnapshot } from "@/api";

/** A node as the API returns it (layer, type, depth, areas, degrees, preview, properties). */
export type GNode = GraphNode;

/** A link between two page ids. `shared` links are drawn between concepts that share sources. */
export interface GLink {
  source: string;
  target: string;
  kind: "wikilink" | "related" | "book" | "shared";
  shared?: number;
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
}

export function toModel(snap: GraphSnapshot): GraphModel {
  return {
    nodes: snap.nodes,
    links: snap.links.map((l) => ({
      source: l.source,
      target: l.target,
      kind: l.kind === "related" || l.kind === "book" ? l.kind : "wikilink",
    })),
    conceptLinks: snap.concept_links.map((c) => ({ source: c.source, target: c.target, shared: c.shared })),
  };
}

export const degreeOf = (n: GNode): number => (n.inDegree || 0) + (n.outDegree || 0);
