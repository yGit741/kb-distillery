import { degreeOf, type GNode } from "./types";

/**
 * What a first-time reader should see: the "Map" view and a public snapshot draw only pages that pass
 * this rule, so a vault full of catalog stubs and bulk imports still reads as a map of ideas.
 *   - concepts (topics, ideas, questions, people) and collections: kept when at least one link reaches them
 *     (topics always: they anchor the layout);
 *   - sources: only the ones read in depth (full or deep) — a listed or skimmed import is not knowledge yet;
 *   - aux types (scopes, distilled think notes) never.
 * One rule, two consumers: the Map story here and, next, the public snapshot build (`share snapshot
 * --predicate public`, to be added in src/kb_distillery/publish/site so the published data carries only these pages).
 */
export const PUBLIC_PREDICATE_ID = "public" as const;
export type Predicate = typeof PUBLIC_PREDICATE_ID;

const AUX = new Set(["scope", "distilled-think"]);
const DEEP = new Set(["full", "deep"]);

export function isPublic(n: GNode): boolean {
  if (AUX.has(n.type)) return false;
  if (n.type === "topic") return true;
  if (n.layer === "source") return DEEP.has(n.depth ?? "");
  return degreeOf(n) >= 1;
}

export const predicateFn = (id: Predicate | null | undefined): ((n: GNode) => boolean) | null => (id === PUBLIC_PREDICATE_ID ? isPublic : null);
