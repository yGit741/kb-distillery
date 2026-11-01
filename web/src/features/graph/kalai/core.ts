import type { GNode, GraphModel } from "../types";

/** A seeded uniform [0, 1) generator (mulberry32): every experiment is reproducible from its seed. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Hub pages (topics, collections) link to everything in their theme; most analyses leave them out. */
export const isHub = (n: GNode): boolean => n.type === "topic" || n.layer === "collection";

/** The undirected page graph: wikilinks weigh 1, a concept link weighs its shared sources. */
export interface PageGraph {
  ids: string[];
  index: Map<string, number>;
  /** each undirected edge once, a < b */
  edges: { a: number; b: number; w: number }[];
}

export function pageGraph(model: GraphModel, opts: { hubs?: boolean } = {}): PageGraph {
  const keep = model.nodes.filter((n) => opts.hubs || !isHub(n));
  const ids = keep.map((n) => n.id);
  const index = new Map(ids.map((id, i) => [id, i]));
  const w = new Map<string, number>();
  const put = (s: string, t: string, weight: number) => {
    const a = index.get(s);
    const b = index.get(t);
    if (a === undefined || b === undefined || a === b) return;
    const key = a < b ? `${a},${b}` : `${b},${a}`;
    w.set(key, Math.max(w.get(key) ?? 0, weight));
  };
  for (const l of model.links) put(l.source, l.target, 1);
  for (const c of model.conceptLinks) put(c.source, c.target, Math.max(1, c.shared));
  const edges = [...w].map(([k, weight]) => {
    const [a, b] = k.split(",").map(Number) as [number, number];
    return { a, b, w: weight };
  });
  return { ids, index, edges };
}

/** Themes = the areas of the topic pages (one per whitelisted theme); falls back to every area seen. */
export function themesOf(nodes: readonly GNode[]): string[] {
  const topics = new Set(nodes.filter((n) => n.type === "topic").flatMap((n) => n.areas.slice(0, 1)));
  const pool = topics.size ? topics : new Set(nodes.flatMap((n) => n.areas));
  return [...pool].sort();
}

export class UnionFind {
  parent: Int32Array;
  size: Int32Array;
  constructor(n: number) {
    this.parent = Int32Array.from({ length: n }, (_, i) => i);
    this.size = new Int32Array(n).fill(1);
  }
  find(x: number): number {
    while (this.parent[x] !== x) {
      const p = this.parent[x] as number;
      this.parent[x] = this.parent[p] as number;
      x = p;
    }
    return x;
  }
  /** Returns the new root, or -1 when already joined. */
  union(a: number, b: number): number {
    let ra = this.find(a);
    let rb = this.find(b);
    if (ra === rb) return -1;
    if ((this.size[ra] as number) < (this.size[rb] as number)) [ra, rb] = [rb, ra];
    this.parent[rb] = ra;
    this.size[ra] = (this.size[ra] as number) + (this.size[rb] as number);
    return ra;
  }
}

type Adj = Map<number, number>[];

function adjacency(n: number, edges: readonly { a: number; b: number; w: number }[]): Adj {
  const adj: Adj = Array.from({ length: n }, () => new Map());
  for (const e of edges) {
    (adj[e.a] as Map<number, number>).set(e.b, ((adj[e.a] as Map<number, number>).get(e.b) ?? 0) + e.w);
    (adj[e.b] as Map<number, number>).set(e.a, ((adj[e.b] as Map<number, number>).get(e.a) ?? 0) + e.w);
  }
  return adj;
}

/**
 * Louvain modularity clustering (local moves, then aggregation, until nothing moves). The visiting order
 * comes from `seed`, so the same graph and seed always give the same clusters: differences between runs
 * are the data's, not the algorithm's.
 */
export function louvain(n: number, edges: readonly { a: number; b: number; w: number }[], seed = 1): Int32Array {
  const rand = rng(seed);
  let adj = adjacency(n, edges);
  let self = new Float64Array(n);
  const member = Int32Array.from({ length: n }, (_, i) => i);
  for (let level = 0; level < 12; level++) {
    const size = adj.length;
    const k = new Float64Array(size);
    let m2 = 0;
    for (let i = 0; i < size; i++) {
      let s = 2 * (self[i] as number);
      for (const w of (adj[i] as Map<number, number>).values()) s += w;
      k[i] = s;
      m2 += s;
    }
    if (m2 === 0) break;
    const comm = Int32Array.from({ length: size }, (_, i) => i);
    const tot = Float64Array.from(k);
    const order = Array.from({ length: size }, (_, i) => i);
    for (let i = size - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [order[i], order[j]] = [order[j] as number, order[i] as number];
    }
    let movedAny = false;
    for (let pass = 0; pass < 30; pass++) {
      let moved = false;
      for (const i of order) {
        const ci = comm[i] as number;
        const ki = k[i] as number;
        tot[ci] = (tot[ci] as number) - ki;
        const wTo = new Map<number, number>();
        for (const [j, w] of adj[i] as Map<number, number>) wTo.set(comm[j] as number, (wTo.get(comm[j] as number) ?? 0) + w);
        let best = ci;
        let bestGain = (wTo.get(ci) ?? 0) - ((tot[ci] as number) * ki) / m2;
        for (const [c, w] of wTo) {
          const gain = w - ((tot[c] as number) * ki) / m2;
          if (gain > bestGain + 1e-12) {
            best = c;
            bestGain = gain;
          }
        }
        tot[best] = (tot[best] as number) + ki;
        if (best !== ci) {
          comm[i] = best;
          moved = true;
        }
      }
      if (!moved) break;
      movedAny = true;
    }
    if (!movedAny) break;
    // renumber and fold every community into one node
    const renum = new Map<number, number>();
    for (let i = 0; i < size; i++) if (!renum.has(comm[i] as number)) renum.set(comm[i] as number, renum.size);
    const next: Adj = Array.from({ length: renum.size }, () => new Map());
    const nextSelf = new Float64Array(renum.size);
    for (let i = 0; i < size; i++) {
      const ci = renum.get(comm[i] as number) as number;
      nextSelf[ci] = (nextSelf[ci] as number) + (self[i] as number);
      for (const [j, w] of adj[i] as Map<number, number>) {
        const cj = renum.get(comm[j] as number) as number;
        if (ci === cj) nextSelf[ci] = (nextSelf[ci] as number) + w / 2;
        else (next[ci] as Map<number, number>).set(cj, ((next[ci] as Map<number, number>).get(cj) ?? 0) + w);
      }
    }
    for (let v = 0; v < n; v++) member[v] = renum.get(comm[member[v] as number] as number) as number;
    adj = next;
    self = nextSelf;
  }
  return member;
}

/** Weighted PageRank on the undirected graph (damping 0.85, isolated pages spread uniformly). */
export function pagerank(n: number, edges: readonly { a: number; b: number; w: number }[], iters = 40): Float64Array {
  const adj = adjacency(n, edges);
  const deg = adj.map((m) => [...m.values()].reduce((s, w) => s + w, 0));
  let pr = new Float64Array(n).fill(1 / Math.max(1, n));
  for (let it = 0; it < iters; it++) {
    const next = new Float64Array(n);
    let dangling = 0;
    for (let i = 0; i < n; i++) {
      const d = deg[i] as number;
      if (d === 0) {
        dangling += pr[i] as number;
        continue;
      }
      for (const [j, w] of adj[i] as Map<number, number>) next[j] = (next[j] as number) + (0.85 * (pr[i] as number) * w) / d;
    }
    const base = (0.15 + 0.85 * dangling) / n;
    for (let i = 0; i < n; i++) next[i] = (next[i] as number) + base;
    pr = next;
  }
  return pr;
}

/** Yield to the browser between heavy steps so a long experiment keeps the page responsive. */
export const breathe = (): Promise<void> => new Promise((r) => setTimeout(r, 0));
