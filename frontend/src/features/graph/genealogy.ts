import type { CitationGraph } from "@/api";

export const GENEALOGY_HOPS = 2;

export type Role = "focus" | "cited" | "citing";

export interface GenealogyNode {
  id: string;
  title: string;
  year: number | null;
  citationCount: number;
  role: Role;
}

export interface Genealogy {
  focus: string;
  nodes: GenealogyNode[];
  links: { source: string; target: string }[];
  /** papers the focus cites, within the hops */
  cited: number;
  /** papers that cite the focus, within the hops */
  citing: number;
}

function walk(adj: ReadonlyMap<string, string[]>, focus: string, hops: number): Set<string> {
  const seen = new Set([focus]);
  let front = [focus];
  for (let h = 0; h < hops && front.length; h++) {
    const next: string[] = [];
    for (const id of front) {
      for (const m of adj.get(id) ?? []) {
        if (!seen.has(m)) {
          seen.add(m);
          next.push(m);
        }
      }
    }
    front = next;
  }
  seen.delete(focus);
  return seen;
}

/**
 * One paper's citation genealogy: what it cites and what cites it, `hops` steps each way. Only papers
 * `isSource` accepts survive (the cataloged source papers: the citation file also names papers that
 * have no page here). Null when the focus has no citation data.
 */
export function genealogyOf(
  c: Pick<CitationGraph, "nodes" | "links">,
  focus: string,
  isSource: (id: string) => boolean,
  hops = GENEALOGY_HOPS,
): Genealogy | null {
  const known = new Set(c.nodes.map((n) => n.id));
  if (!known.has(focus)) return null;
  const links = c.links.filter((l) => isSource(l.source) && isSource(l.target));
  const refs = new Map<string, string[]>();
  const citers = new Map<string, string[]>();
  for (const l of links) {
    (refs.get(l.source) ?? refs.set(l.source, []).get(l.source))?.push(l.target);
    (citers.get(l.target) ?? citers.set(l.target, []).get(l.target))?.push(l.source);
  }
  const cited = walk(refs, focus, hops);
  const citing = walk(citers, focus, hops);
  const keep = new Set([focus, ...cited, ...citing]);
  const role = (id: string): Role => (id === focus ? "focus" : citing.has(id) ? "citing" : "cited");
  return {
    focus,
    nodes: c.nodes
      .filter((n) => keep.has(n.id) && isSource(n.id))
      .map((n) => ({ id: n.id, title: n.title, year: n.year ?? null, citationCount: n.citationCount, role: role(n.id) })),
    links: links.filter((l) => keep.has(l.source) && keep.has(l.target)).map((l) => ({ source: l.source, target: l.target })),
    cited: cited.size,
    citing: citing.size,
  };
}
