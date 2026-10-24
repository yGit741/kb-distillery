import type { GraphModel } from "../types";
import { breathe, louvain, pageGraph, pagerank, rng, type PageGraph } from "./core";

/**
 * Noise stability (Benjamini–Kalai–Schramm): perturb the input a little and ask which conclusions survive.
 * The input here is the vault: drop a random eps of the links (a link I never wrote) or of the sources (a
 * paper I never read), re-run the clustering and the ranking, and compare with the unperturbed run.
 *   - cluster stability of a page = mean Jaccard of its cluster, perturbed vs baseline (1 = always the same company)
 *   - rank stability of a top page = share of runs in which it stays in the top K
 * A conclusion that flips under 10% noise is noise-sensitive: do not build a thesis argument on it.
 */

export type NoiseMode = "links" | "sources";

export interface NoiseOptions {
  eps: number;
  mode?: NoiseMode;
  runs?: number;
  topK?: number;
  hubs?: boolean;
  seed?: number;
  /** rank only concept pages (ideas, questions, people): "what is central in my thinking" */
  conceptsOnly?: boolean;
  onProgress?: (done: number, total: number) => void;
}

export interface NoiseResult {
  eps: number;
  mode: NoiseMode;
  runs: number;
  /** page id -> mean Jaccard of its cluster against the baseline */
  clusterStability: Map<string, number>;
  /** baseline top-K page ids, best first */
  top: string[];
  /** page id -> share of runs in which it stayed in the top K */
  topKeep: Map<string, number>;
  /** baseline cluster of every page (index into `clusters`) */
  cluster: Map<string, number>;
  clusterCount: number;
  meanStability: number;
  meanTopKeep: number;
}

/** Per-page Jaccard of its cluster in two partitions, from the contingency table (O(n)). */
export function clusterJaccard(base: Int32Array, other: Int32Array): Float64Array {
  const sizeA = new Map<number, number>();
  const sizeB = new Map<number, number>();
  const both = new Map<string, number>();
  for (let i = 0; i < base.length; i++) {
    const a = base[i] as number;
    const b = other[i] as number;
    sizeA.set(a, (sizeA.get(a) ?? 0) + 1);
    sizeB.set(b, (sizeB.get(b) ?? 0) + 1);
    both.set(`${a},${b}`, (both.get(`${a},${b}`) ?? 0) + 1);
  }
  return Float64Array.from(base, (a, i) => {
    const b = other[i] as number;
    const inter = both.get(`${a},${b}`) as number;
    return inter / ((sizeA.get(a) as number) + (sizeB.get(b) as number) - inter);
  });
}

function ranked(pr: Float64Array, eligible: (i: number) => boolean, k: number): number[] {
  return [...pr.keys()].filter(eligible).sort((a, b) => (pr[b] as number) - (pr[a] as number)).slice(0, k);
}

export function perturb(g: PageGraph, mode: NoiseMode, eps: number, rand: () => number, isSource: (i: number) => boolean) {
  if (mode === "links") return g.edges.filter(() => rand() >= eps);
  const dropped = new Set<number>();
  for (let i = 0; i < g.ids.length; i++) if (isSource(i) && rand() < eps) dropped.add(i);
  return g.edges.filter((e) => !dropped.has(e.a) && !dropped.has(e.b));
}

export async function noiseStability(model: GraphModel, opts: NoiseOptions): Promise<NoiseResult> {
  const mode = opts.mode ?? "links";
  const runs = opts.runs ?? 10;
  const k = opts.topK ?? 20;
  const g = pageGraph(model, { hubs: opts.hubs });
  const byId = new Map(model.nodes.map((n) => [n.id, n]));
  const layer = (i: number) => byId.get(g.ids[i] as string)?.layer;
  const eligible = opts.conceptsOnly === false ? () => true : (i: number) => layer(i) === "concept";
  const n = g.ids.length;
  const base = louvain(n, g.edges, 1);
  const top = ranked(pagerank(n, g.edges), eligible, k);
  const stab = new Float64Array(n);
  const keep = new Map(top.map((i) => [i, 0]));
  const rand = rng(opts.seed ?? 42);
  for (let r = 0; r < runs; r++) {
    const edges = perturb(g, mode, opts.eps, rand, (i) => layer(i) === "source");
    const j = clusterJaccard(base, louvain(n, edges, 1));
    for (let i = 0; i < n; i++) stab[i] = (stab[i] as number) + (j[i] as number) / runs;
    for (const i of ranked(pagerank(n, edges), eligible, k)) if (keep.has(i)) keep.set(i, (keep.get(i) as number) + 1 / runs);
    opts.onProgress?.(r + 1, runs);
    await breathe();
  }
  const clusterStability = new Map(g.ids.map((id, i) => [id, stab[i] as number]));
  const topKeep = new Map([...keep].map(([i, v]) => [g.ids[i] as string, v]));
  return {
    eps: opts.eps,
    mode,
    runs,
    clusterStability,
    top: top.map((i) => g.ids[i] as string),
    topKeep,
    cluster: new Map(g.ids.map((id, i) => [id, base[i] as number])),
    clusterCount: new Set(base).size,
    meanStability: n ? stab.reduce((s, v) => s + v, 0) / n : 1,
    meanTopKeep: top.length ? [...keep.values()].reduce((s, v) => s + v, 0) / top.length : 1,
  };
}

/** The stability curve: how fast conclusions decay as the noise grows (a short run per eps). */
export async function stabilityCurve(model: GraphModel, opts: Omit<NoiseOptions, "eps"> & { eps: readonly number[] }) {
  const out: { eps: number; meanStability: number; meanTopKeep: number }[] = [];
  for (const eps of opts.eps) {
    const r = await noiseStability(model, { ...opts, eps, runs: opts.runs ?? 4, onProgress: undefined });
    out.push({ eps, meanStability: r.meanStability, meanTopKeep: r.meanTopKeep });
    opts.onProgress?.(out.length, opts.eps.length);
  }
  return out;
}
