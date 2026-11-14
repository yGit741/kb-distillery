import type { ColorBy } from "./style";

/** The two things the graph can be about: the concepts I think with, or the sources I read. */
export type GraphSubject = "concepts" | "sources";

export interface Dimension {
  by: ColorBy;
  /** as the legend header says it: "Color by theme" */
  label: string;
}

/** What the legend's "Color by" offers for each subject: only colourings that answer a question about it. */
export const DIMENSIONS: Readonly<Record<GraphSubject, readonly Dimension[]>> = {
  concepts: [
    { by: "area", label: "theme" },
    { by: "format", label: "type" },
    { by: "status", label: "maturity" },
    { by: "recency", label: "recency" },
    { by: "evidence", label: "source count" },
  ],
  sources: [
    { by: "format", label: "format" },
    { by: "depth", label: "digest status" },
    { by: "added", label: "date added" },
  ],
};

/**
 * The dimensions on offer for what is drawn: the concept ones, and the source ones once sources are on screen
 * (a colouring both lists share appears once, under the name of the first).
 */
export function dimensionsFor(subjects: readonly GraphSubject[]): Dimension[] {
  const out: Dimension[] = [];
  for (const s of subjects) for (const d of DIMENSIONS[s]) if (!out.some((o) => o.by === d.by)) out.push(d);
  return out;
}
