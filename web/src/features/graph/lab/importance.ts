import type { NeighborMap } from "../graphData";
import type { GNode } from "../types";
import { DEPTH_WEIGHT, TYPE_RANK, type LabConfig } from "./config";

/** Each signal in 0..1 (after normalisation); the score is their weighted mean. */
export interface Terms {
  tier: number;
  evidence: number;
  degree: number;
  pagerank: number;
  between: number;
  open: number;
  gap: number;
  orphan: number;
}

export interface Importance {
  score: Map<string, number>;
  terms: Map<string, Terms>;
  /** 0 = most important visible page, 1 = least. */
  qrank: Map<string, number>;
  maxScore: number;
}

/** Types with fewer drawn pages than this are normalised on the global scale instead of by percentile. */
export const MIN_TYPE_FOR_PERCENTILE = 5;

export const TERM_WEIGHTS: readonly [keyof Terms, keyof LabConfig][] = [
  ["tier", "wTier"],
  ["evidence", "wEvidence"],
  ["degree", "wDegree"],
  ["pagerank", "wPagerank"],
  ["between", "wBetween"],
  ["open", "wOpen"],
  ["gap", "wGap"],
  ["orphan", "wOrphan"],
];

/** Neighbours of every visible page that are themselves visible. */
export function visibleAdjacency(visible: ReadonlySet<string>, neighbors: NeighborMap): Map<string, string[]> {
  const adj = new Map<string, string[]>();
  for (const id of visible) adj.set(id, [...new Set(neighbors.get(id) ?? [])].filter((j) => j !== id && visible.has(j)));
  return adj;
}

export function pagerank(adj: ReadonlyMap<string, readonly string[]>, iterations = 30): Map<string, number> {
  const ids = [...adj.keys()];
  const n = ids.length || 1;
  let pr = new Map(ids.map((id) => [id, 1 / n]));
  for (let it = 0; it < iterations; it++) {
    const next = new Map(ids.map((id) => [id, 0.15 / n]));
    for (const id of ids) {
      const out = adj.get(id) ?? [];
      if (!out.length) continue;
      const share = (0.85 * (pr.get(id) ?? 0)) / out.length;
      for (const m of out) next.set(m, (next.get(m) ?? 0) + share);
    }
    pr = next;
  }
  return pr;
}

/** Brandes betweenness centrality, unweighted, undirected. */
export function betweenness(adj: ReadonlyMap<string, readonly string[]>): Map<string, number> {
  const ids = [...adj.keys()];
  const idx = new Map(ids.map((id, i) => [id, i]));
  const N = ids.length;
  const nb = ids.map((id) => (adj.get(id) ?? []).map((j) => idx.get(j)).filter((j): j is number => j !== undefined));
  const cb = new Float64Array(N);
  const sigma = new Float64Array(N);
  const dist = new Int32Array(N);
  const delta = new Float64Array(N);
  const queue = new Int32Array(N);
  const preds: number[][] = Array.from({ length: N }, () => []);
  const stack: number[] = [];
  for (let s = 0; s < N; s++) {
    stack.length = 0;
    for (let i = 0; i < N; i++) {
      (preds[i] as number[]).length = 0;
      sigma[i] = 0;
      dist[i] = -1;
      delta[i] = 0;
    }
    sigma[s] = 1;
    dist[s] = 0;
    let head = 0;
    let tail = 0;
    queue[tail++] = s;
    while (head < tail) {
      const v = queue[head++] as number;
      stack.push(v);
      for (const w of nb[v] as number[]) {
        if ((dist[w] as number) < 0) {
          dist[w] = (dist[v] as number) + 1;
          queue[tail++] = w;
        }
        if (dist[w] === (dist[v] as number) + 1) {
          sigma[w] = (sigma[w] as number) + (sigma[v] as number);
          (preds[w] as number[]).push(v);
        }
      }
    }
    while (stack.length) {
      const w = stack.pop() as number;
      for (const v of preds[w] as number[]) delta[v] = (delta[v] as number) + ((sigma[v] as number) / (sigma[w] as number)) * (1 + (delta[w] as number));
      if (w !== s) cb[w] = (cb[w] as number) + (delta[w] as number);
    }
  }
  return new Map(ids.map((id, i) => [id, cb[i] as number]));
}

/** Percentile rank of each item by `value` (ties share the higher rank). */
function percentile(items: readonly string[], value: (id: string) => number): Map<string, number> {
  const sorted = [...items].sort((a, b) => value(a) - value(b));
  const out = new Map<string, number>();
  const last = sorted.length - 1;
  for (let i = last; i >= 0; i--) {
    const id = sorted[i] as string;
    const nextId = sorted[i + 1];
    out.set(id, nextId !== undefined && value(nextId) === value(id) ? (out.get(nextId) as number) : last > 0 ? i / last : 1);
  }
  return out;
}

export interface ImportanceInput {
  visible: ReadonlySet<string>;
  byId: ReadonlyMap<string, GNode>;
  neighbors: NeighborMap;
  cfg: LabConfig;
}

/**
 * Score every visible page. Signals are normalised within their type (a top article and a top idea both get
 * a high percentile) or across the graph; the type tier then decides between types. Raw link count is one
 * signal among many and off by default: in this vault it measures bulk imports, not importance.
 */
export function computeImportance({ visible, byId, neighbors, cfg }: ImportanceInput): Importance {
  const ids = [...visible].filter((id) => byId.has(id));
  const adj = visibleAdjacency(new Set(ids), neighbors);
  const pr = cfg.wPagerank ? pagerank(adj) : null;
  const bt = cfg.wBetween ? betweenness(adj) : null;
  const dw: Record<string, number> = { ...DEPTH_WEIGHT, easy: cfg.easyWeight };
  const raw = new Map<string, { ev: number; deg: number; pr: number; bt: number }>();
  for (const id of ids) {
    const n = byId.get(id) as GNode;
    // a source is evidence by its own depth; a collection by the mean depth of its members (an aggregate, so a
    // bulk import is not "much evidence"); any other page by the depth-weighted sum of its neighbouring sources
    let ev = 0;
    let members = 0;
    if (n.layer === "source") ev = dw[n.depth] ?? 0;
    else for (const j of new Set(neighbors.get(id) ?? [])) {
      const m = byId.get(j);
      if (m?.layer !== "source") continue;
      ev += dw[m.depth] ?? 0;
      members++;
    }
    if (n.layer === "collection" && members) ev /= members;
    const deg =
      cfg.degBasis === "all"
        ? (n.inDegree || 0) + (n.outDegree || 0)
        : cfg.degBasis === "nohub"
          ? (adj.get(id) ?? []).filter((j) => byId.get(j)?.layer !== "collection").length
          : (adj.get(id) ?? []).length;
    raw.set(id, { ev: Math.log1p(ev), deg: Math.log1p(deg), pr: pr?.get(id) ?? 0, bt: Math.sqrt(bt?.get(id) ?? 0) });
  }
  const norm = { ev: new Map<string, number>(), deg: new Map<string, number>(), pr: new Map<string, number>(), bt: new Map<string, number>() };
  const byType = new Map<string, string[]>();
  for (const id of ids) {
    const t = (byId.get(id) as GNode).type;
    const list = byType.get(t);
    if (list) list.push(id);
    else byType.set(t, [id]);
  }
  for (const k of ["ev", "deg", "pr", "bt"] as const) {
    const val = (id: string) => (raw.get(id) as Record<typeof k, number>)[k];
    const gmax = Math.max(0, ...ids.map(val)) || 1;
    if (cfg.norm === "type" && k !== "bt") {
      for (const list of byType.values()) {
        // a percentile of two pages says nothing: small types use the global scale
        if (list.length < MIN_TYPE_FOR_PERCENTILE) {
          for (const id of list) norm[k].set(id, val(id) / gmax);
          continue;
        }
        const mx = Math.max(0, ...list.map(val));
        const p = percentile(list, val);
        for (const id of list) norm[k].set(id, mx > 0 ? (p.get(id) as number) : 0);
      }
    } else {
      for (const id of ids) norm[k].set(id, val(id) / gmax);
    }
  }
  const wsum = TERM_WEIGHTS.reduce((a, [, w]) => a + (cfg[w] as number), 0) || 1;
  const terms = new Map<string, Terms>();
  const score = new Map<string, number>();
  for (const id of ids) {
    const n = byId.get(id) as GNode;
    const evidence = norm.ev.get(id) ?? 0;
    const degree = norm.deg.get(id) ?? 0;
    const t: Terms = {
      tier: TYPE_RANK[n.type] ?? 0.2,
      evidence,
      degree,
      pagerank: norm.pr.get(id) ?? 0,
      between: norm.bt.get(id) ?? 0,
      open: n.type === "question" && /open|partial/.test(n.maturity) ? 1 : 0,
      gap: n.layer === "source" ? degree * (1 - (DEPTH_WEIGHT[n.depth] ?? 0) / 3) : degree * (1 - evidence),
      orphan: (adj.get(id) ?? []).length <= 1 ? 1 : 0,
    };
    terms.set(id, t);
    score.set(id, TERM_WEIGHTS.reduce((a, [k, w]) => a + (cfg[w] as number) * t[k], 0) / wsum);
  }
  const ranked = [...ids].sort((a, b) => (score.get(b) as number) - (score.get(a) as number) || a.localeCompare(b));
  const qrank = new Map(ranked.map((id, i) => [id, i / Math.max(1, ranked.length - 1)]));
  return { score, terms, qrank, maxScore: score.get(ranked[0] ?? "") || 1 };
}

/** Hop distance from the selection, up to `max` hops, over visible pages. */
export function hopsFrom(start: Iterable<string>, visible: ReadonlySet<string>, neighbors: NeighborMap, max = 3): Map<string, number> {
  const hops = new Map<string, number>();
  let frontier: string[] = [];
  for (const id of start) if (visible.has(id)) {
    hops.set(id, 0);
    frontier.push(id);
  }
  for (let d = 1; d <= max && frontier.length; d++) {
    const next: string[] = [];
    for (const id of frontier) for (const j of neighbors.get(id) ?? []) {
      if (visible.has(j) && !hops.has(j)) {
        hops.set(j, d);
        next.push(j);
      }
    }
    frontier = next;
  }
  return hops;
}
