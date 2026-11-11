import type { CitationGraph } from "@/api";
import { withAlpha } from "./canvasTheme";

/** How far a paper got: no citation data (failed / never fetched), then its digest depth. Ordered red -> green. */
export type CiteStatus = "failed" | "listed" | "easy" | "full" | "deep";
export const CITE_STATUS: readonly { key: CiteStatus; label: string }[] = [
  { key: "failed", label: "no citation data" },
  { key: "listed", label: "fetched, listed" },
  { key: "easy", label: "easy digest" },
  { key: "full", label: "full digest" },
  { key: "deep", label: "deep digest" },
];

/**
 * The status ramp from the app's central status tokens: --bad for a failure, then --ok at growing strength (light
 * green for a listed paper, the full green for a deep digest). No hex of its own.
 */
export function statusRamp(ok: string, bad: string): Record<CiteStatus, string> {
  return { failed: bad, listed: withAlpha(ok, 0.3), easy: withAlpha(ok, 0.5), full: withAlpha(ok, 0.75), deep: withAlpha(ok, 1) };
}

export interface CitationMapNode {
  id: string;
  title: string;
  year: number | null;
  citationCount: number;
  status: CiteStatus;
  /** no cites link to or from another cataloged paper */
  isolated: boolean;
}

export interface CitationMapData {
  nodes: CitationMapNode[];
  links: { source: string; target: string }[];
  /** cataloged papers in the citation data */
  papers: number;
  /** papers with at least one cites link among cataloged papers */
  linked: number;
  /** vault papers the citation data does not cover (a fetch miss, or never fetched): the red nodes */
  withoutData: number;
}

export interface VaultPaper {
  id: string;
  title: string;
  depth?: string | null;
  year?: number | null;
}

const DEPTHS = new Set<string>(["listed", "easy", "full", "deep"]);
const statusOf = (depth: string | null | undefined): CiteStatus => (depth && DEPTHS.has(depth) ? (depth as CiteStatus) : "listed");

/**
 * The corpus-wide citation map: every cataloged paper of GET /api/citations (`isSource`) with the cites links
 * among them (source cites target; self links, links leaving the catalog and duplicates are dropped), plus every
 * vault paper (`papers`) the citation data lacks, as an unlinked "failed" node so the gaps stay visible.
 */
export function citationMap(g: Pick<CitationGraph, "nodes" | "links">, isSource: (id: string) => boolean, papers: readonly VaultPaper[] = []): CitationMapData {
  const depthOf = new Map(papers.map((p) => [p.id, p.depth]));
  const kept = g.nodes.filter((n) => isSource(n.id));
  const ids = new Set(kept.map((n) => n.id));
  const seen = new Set<string>();
  const links: { source: string; target: string }[] = [];
  const touched = new Set<string>();
  for (const l of g.links) {
    if (l.source === l.target || !ids.has(l.source) || !ids.has(l.target)) continue;
    const k = `${l.source}\u0000${l.target}`;
    if (seen.has(k)) continue;
    seen.add(k);
    links.push({ source: l.source, target: l.target });
    touched.add(l.source).add(l.target);
  }
  const nodes: CitationMapNode[] = kept.map((n) => ({
    id: n.id,
    title: n.title,
    year: n.year ?? null,
    citationCount: n.citationCount ?? 0,
    status: statusOf(depthOf.get(n.id)),
    isolated: !touched.has(n.id),
  }));
  let withoutData = 0;
  for (const p of papers) {
    if (ids.has(p.id)) continue;
    withoutData++;
    nodes.push({ id: p.id, title: p.title, year: p.year ?? null, citationCount: 0, status: "failed", isolated: true });
  }
  return { nodes, links, papers: kept.length, linked: touched.size, withoutData };
}

/** Grid spacing (graph units) of the papers without citation data, and the gap between them and the linked core. */
export const MISSING_STEP = 12;
const MISSING_GAP = 50;

/**
 * Fixed spots for the papers without citation data: a loose grid to the right of the linked core (the force layout
 * centres the core near the origin), so the failures stay visible without swamping the core. `coreRight` is the
 * core's right edge once known.
 */
export function missingGrid(count: number, coreRight = 150, coreMidY = 0): { x: number; y: number }[] {
  const cols = Math.max(1, Math.ceil(Math.sqrt(count * 0.75)));
  const rows = Math.ceil(count / cols);
  const y0 = coreMidY - ((rows - 1) * MISSING_STEP) / 2;
  return Array.from({ length: count }, (_, i) => ({ x: coreRight + MISSING_GAP + (i % cols) * MISSING_STEP, y: y0 + Math.floor(i / cols) * MISSING_STEP }));
}
