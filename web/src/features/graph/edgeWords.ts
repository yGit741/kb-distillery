import { selectable } from "./edgeSelect";
import type { SimLink } from "./types";

/** At most this many drawn edges for the standing words: past it the graph is too dense to write on. */
export const MAX_WORDED_EDGES = 60;

/** What tells two edges apart: a typed relation by its name, every other link by its kind. */
export const edgeType = (l: Pick<SimLink, "kind" | "rel">): string => (l.kind === "related" && l.rel ? `related:${l.rel}` : l.kind);

/**
 * The edges that carry their words standing (not only when lit): on a sparse graph whose edges are of two types or
 * more, every drawn edge, so the reader sees which is which without hovering. Otherwise none.
 */
export function wordedEdges(links: readonly SimLink[], hiddenKinds: ReadonlySet<string>): SimLink[] {
  const drawn = links.filter((l) => selectable(l) && !hiddenKinds.has(l.kind));
  if (!drawn.length || drawn.length > MAX_WORDED_EDGES) return [];
  return new Set(drawn.map(edgeType)).size >= 2 ? drawn : [];
}
