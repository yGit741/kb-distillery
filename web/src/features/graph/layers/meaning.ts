import { FOCUS, type Layer, type NodeCond } from "./model";

/**
 * Meaning in the layer language (flags graph-intent and semantic-search): an `about "phrase"` condition is asked of the
 * meaning service once, before the layer is previewed or applied, and keeps the top pages it names beside the phrase, so
 * the chip still reads `about "overfitting"` while `evaluate` (synchronous) works on concrete slugs.
 */

/** How many pages one `about` keeps. */
export const SIMILAR_K = 20;

/** Asks the service: pages close to a phrase (`q`) or to a page's own card (`slug`), best first. Rejects when it cannot answer. */
export type Similar = (ask: { q?: string; slug?: string; k: number }) => Promise<string[]>;

/** Answers kept for the session, one per phrase (or page), so editing a sentence does not ask again. */
const cache = new Map<string, Promise<string[]>>();
export const clearMeaningCache = () => cache.clear();

const conds = (l: Layer): NodeCond[] => l.subgraph.nodes ?? [];
const aboutIn = (c: NodeCond): Extract<NodeCond, { t: "about" }>[] => (c.t === "about" ? [c] : c.t === "not" ? aboutIn(c.cond) : []);

/** Whether any layer holds an `about` that still needs an answer. */
export const needsMeaning = (layers: readonly Layer[]): boolean => layers.some((l) => conds(l).some((c) => aboutIn(c).some((a) => !a.slugs)));

export type Resolution = { ok: true; layers: Layer[] } | { ok: false; reason: "focus" };

/**
 * The layers with every `about` answered. `focus` is the one focused page ("similar to this"); an `about "$focus"` with no
 * focus stops here. A condition the service cannot answer (no `similar`, off, down) stays as it was, so `evaluate` skips it
 * with its reason and the rest of the sentence still applies.
 */
export async function resolveAbout(layers: Layer[], similar: Similar | null, focus?: string): Promise<Resolution> {
  const asks = layers.flatMap((l) => conds(l).flatMap(aboutIn)).filter((a) => !a.slugs);
  if (asks.some((a) => a.phrase === FOCUS && !a.slug && !focus)) return { ok: false, reason: "focus" };
  if (!similar || !asks.length) return { ok: true, layers };
  const ask = (a: Extract<NodeCond, { t: "about" }>): Promise<string[]> => {
    const slug = a.slug ?? (a.phrase === FOCUS ? focus : undefined);
    const key = slug ? `slug:${slug}` : `q:${a.phrase.trim().toLowerCase()}`;
    let hit = cache.get(key);
    if (!hit) {
      hit = similar({ ...(slug ? { slug } : { q: a.phrase }), k: SIMILAR_K });
      cache.set(key, hit);
      hit.catch(() => cache.delete(key));
    }
    return hit;
  };
  const answers = new Map<Extract<NodeCond, { t: "about" }>, string[] | null>();
  await Promise.all(asks.map(async (a) => void answers.set(a, await ask(a).catch(() => null))));
  const fill = (c: NodeCond): NodeCond => {
    if (c.t === "not") return { ...c, cond: fill(c.cond) };
    if (c.t !== "about") return c;
    const slugs = answers.get(c);
    return slugs ? { ...c, slugs } : c;
  };
  return {
    ok: true,
    layers: layers.map((l) => (l.subgraph.nodes ? { ...l, subgraph: { ...l.subgraph, nodes: l.subgraph.nodes.map(fill) } } : l)),
  };
}
