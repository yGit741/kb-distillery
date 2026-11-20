/**
 * The graph size the knowledge base menus show and sort by: concept nodes, source nodes and concept-to-concept
 * edges (counted by graph/stats.py on the server).
 */
export interface KbSize {
  concepts: number;
  sources: number;
  edges: number;
}

/** Fewer concepts than this is too small to be a knowledge base yet. */
export const MIN_CONCEPTS = 5;

/** The sort key: the mean of the concept count and the concept-to-concept edge count. */
export const kbScore = (s: KbSize): number => (s.concepts + s.edges) / 2;

/** Why the graph is unhealthy (shown in red), or null: almost no concepts, or concepts that link to none. */
export function kbProblem(s: KbSize): string | null {
  const out: string[] = [];
  if (s.concepts < MIN_CONCEPTS) out.push(`only ${s.concepts} concept${s.concepts === 1 ? "" : "s"}`);
  if (s.concepts > 0 && s.edges === 0) out.push("no links between concepts");
  return out.length ? out.join(", ") : null;
}

/** `rows` largest first by `kbScore`; rows with no size keep their order after the rest. */
export function bySize<T>(rows: readonly T[], size: (r: T) => KbSize | undefined): T[] {
  const key = (r: T) => {
    const s = size(r);
    return s ? kbScore(s) : -1;
  };
  return rows.map((r, i) => [r, i] as const).sort((a, b) => key(b[0]) - key(a[0]) || a[1] - b[1]).map(([r]) => r);
}

export const sizeTitle = (s: KbSize): string =>
  `${s.concepts} concepts · ${s.sources} sources · ${s.edges} edges between concepts`;
