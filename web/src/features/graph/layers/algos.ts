/**
 * Graph-theory measures for `>` lines (flag graph-algos): pure functions over an undirected adjacency, deterministic
 * (pages are visited in id order), no React. Each runs on the pages the screen draws, so its answer is about what is
 * seen. Sizes here are a few thousand pages and links: every function is linear or close to it, except the clique
 * search, which stops after a fixed number of steps and says so.
 */

export type Adj = ReadonlyMap<string, ReadonlySet<string>>;

/** The adjacency restricted to `inside` (links with both ends inside), every page of `inside` present. */
export function within(adj: Adj, inside: Iterable<string>): Map<string, Set<string>> {
  const keep = new Set(inside);
  const out = new Map<string, Set<string>>();
  for (const id of keep) out.set(id, new Set([...(adj.get(id) ?? [])].filter((o) => keep.has(o) && o !== id)));
  return out;
}

const ids = (adj: Adj) => [...adj.keys()].sort();

// ---- cliques
export const CLIQUE_STEPS = 200_000;

/**
 * The pages in a maximal clique of at least `min` pages (Bron–Kerbosch with a pivot). `capped` says the search
 * stopped at CLIQUE_STEPS: the pages found so far are still right, some may be missing.
 */
export function cliques(adj: Adj, min: number): { pages: Set<string>; count: number; capped: boolean } {
  const pages = new Set<string>();
  let count = 0;
  let steps = 0;
  let capped = false;
  const nb = (v: string) => adj.get(v) ?? new Set<string>();
  const expand = (r: string[], p: Set<string>, x: Set<string>) => {
    if (++steps > CLIQUE_STEPS) {
      capped = true;
      return;
    }
    if (!p.size && !x.size) {
      if (r.length >= min) {
        count++;
        for (const v of r) pages.add(v);
      }
      return;
    }
    // a clique that cannot reach `min` any more is not worth growing
    if (r.length + p.size < min) return;
    let pivot = "";
    let best = -1;
    for (const u of [...p, ...x]) {
      let k = 0;
      for (const v of nb(u)) if (p.has(v)) k++;
      if (k > best) [pivot, best] = [u, k];
    }
    for (const v of [...p].filter((v) => !nb(pivot).has(v)).sort()) {
      const nv = nb(v);
      expand([...r, v], new Set([...p].filter((w) => nv.has(w))), new Set([...x].filter((w) => nv.has(w))));
      if (capped) return;
      p.delete(v);
      x.add(v);
    }
  };
  expand([], new Set(ids(adj)), new Set());
  return { pages, count, capped };
}

// ---- cores
/** The k-core: what is left after taking away, again and again, every page with fewer than `k` links. */
export function kCore(adj: Adj, k: number): Set<string> {
  const deg = new Map(ids(adj).map((id) => [id, adj.get(id)!.size] as const));
  const gone = new Set<string>();
  const queue = [...deg].filter(([, d]) => d < k).map(([id]) => id);
  while (queue.length) {
    const id = queue.pop()!;
    if (gone.has(id)) continue;
    gone.add(id);
    for (const o of adj.get(id) ?? [])
      if (!gone.has(o)) {
        const d = deg.get(o)! - 1;
        deg.set(o, d);
        if (d < k) queue.push(o);
      }
  }
  return new Set(ids(adj).filter((id) => !gone.has(id)));
}

// ---- cut vertices and bridges (Tarjan, iterative)
/** Pages whose removal splits their part of the graph (cut vertices), and pages at either end of a bridge link. */
export function cutsAndBridges(adj: Adj): { cuts: Set<string>; bridgeEnds: Set<string>; bridges: [string, string][] } {
  const disc = new Map<string, number>();
  const low = new Map<string, number>();
  const cuts = new Set<string>();
  const bridges: [string, string][] = [];
  let time = 0;
  for (const root of ids(adj)) {
    if (disc.has(root)) continue;
    disc.set(root, time);
    low.set(root, time++);
    let rootKids = 0;
    // frames: page, its parent, its neighbours still to visit
    const stack: { v: string; parent: string | null; rest: string[] }[] = [{ v: root, parent: null, rest: [...(adj.get(root) ?? [])].sort() }];
    while (stack.length) {
      const top = stack[stack.length - 1]!;
      const w = top.rest.shift();
      if (w !== undefined) {
        if (w === top.parent) continue;
        if (disc.has(w)) low.set(top.v, Math.min(low.get(top.v)!, disc.get(w)!));
        else {
          disc.set(w, time);
          low.set(w, time++);
          if (top.v === root) rootKids++;
          stack.push({ v: w, parent: top.v, rest: [...(adj.get(w) ?? [])].sort() });
        }
        continue;
      }
      stack.pop();
      const p = top.parent;
      if (p === null) continue;
      low.set(p, Math.min(low.get(p)!, low.get(top.v)!));
      if (low.get(top.v)! > disc.get(p)!) bridges.push([p, top.v]);
      if (p !== root && low.get(top.v)! >= disc.get(p)!) cuts.add(p);
    }
    if (rootKids > 1) cuts.add(root);
  }
  return { cuts, bridgeEnds: new Set(bridges.flat()), bridges };
}

// ---- centrality
export const SAMPLE_ABOVE = 600;
const SAMPLE_SOURCES = 250;
export type Centrality = "degree" | "betweenness" | "pagerank" | "closeness";

/** A score per page: links (degree), shortest paths through it (betweenness, Brandes), PageRank, or harmonic closeness. */
export function centrality(adj: Adj, by: Centrality): Map<string, number> {
  const all = ids(adj);
  if (by === "degree") return new Map(all.map((id) => [id, adj.get(id)!.size]));
  if (by === "pagerank") {
    const n = all.length || 1;
    let pr = new Map(all.map((id) => [id, 1 / n]));
    for (let it = 0; it < 40; it++) {
      const next = new Map(all.map((id) => [id, 0.15 / n]));
      let dangling = 0;
      for (const id of all) {
        const out = adj.get(id)!;
        if (!out.size) dangling += pr.get(id)!;
        else for (const o of out) next.set(o, next.get(o)! + (0.85 * pr.get(id)!) / out.size);
      }
      for (const id of all) next.set(id, next.get(id)! + (0.85 * dangling) / n);
      pr = next;
    }
    return pr;
  }
  const score = new Map(all.map((id) => [id, 0]));
  // above SAMPLE_ABOVE pages, a fixed, even sample of sources (every k-th page by id), scaled back up: the ranking is
  // what a "top N" reads, and it holds well; a full pass over a thousand pages takes a second
  const step = all.length > SAMPLE_ABOVE ? Math.ceil(all.length / SAMPLE_SOURCES) : 1;
  const sources = all.filter((_, i) => i % step === 0);
  for (const s of sources) {
    // breadth first from s: distances, path counts, and the order pages were reached
    const dist = new Map([[s, 0]]);
    const sigma = new Map([[s, 1]]);
    const preds = new Map<string, string[]>();
    const order: string[] = [];
    const queue = [s];
    for (let i = 0; i < queue.length; i++) {
      const v = queue[i]!;
      order.push(v);
      for (const w of adj.get(v)!) {
        if (!dist.has(w)) {
          dist.set(w, dist.get(v)! + 1);
          queue.push(w);
        }
        if (dist.get(w) === dist.get(v)! + 1) {
          sigma.set(w, (sigma.get(w) ?? 0) + sigma.get(v)!);
          (preds.get(w) ?? preds.set(w, []).get(w)!).push(v);
        }
      }
    }
    if (by === "closeness") {
      // harmonic closeness, summed from the sources' side: distances are the same both ways
      for (const [id, d] of dist) if (id !== s) score.set(id, score.get(id)! + 1 / d);
      continue;
    }
    const delta = new Map<string, number>();
    for (let i = order.length - 1; i >= 0; i--) {
      const w = order[i]!;
      for (const v of preds.get(w) ?? []) delta.set(v, (delta.get(v) ?? 0) + (sigma.get(v)! / sigma.get(w)!) * (1 + (delta.get(w) ?? 0)));
      if (w !== s) score.set(w, score.get(w)! + (delta.get(w) ?? 0));
    }
  }
  // undirected: every pair was counted from both ends; a sample is scaled back to every source
  const scale = (by === "betweenness" ? 0.5 : 1) * (all.length / sources.length);
  for (const id of all) score.set(id, score.get(id)! * scale);
  return score;
}

/** The `n` pages with the highest score, ties by id. */
export function top(scores: ReadonlyMap<string, number>, n: number): Set<string> {
  return new Set([...scores].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, n).map(([id]) => id));
}

// ---- communities (Louvain)
/**
 * Communities by modularity (Louvain: move each page to the neighbouring group that gains most, then fold groups into
 * single pages and repeat). Returns each page's group, numbered 0.. from the largest group down.
 */
export function communities(adj: Adj): Map<string, number> {
  const all = ids(adj);
  const index = new Map(all.map((id, i) => [id, i] as const));
  // the current level: weighted links between its nodes, and which node each page sits in
  let w: Map<number, number>[] = all.map((id) => {
    const m = new Map<number, number>();
    for (const o of adj.get(id)!) m.set(index.get(o)!, 1);
    return m;
  });
  let of = all.map((_, i) => i);
  for (let level = 0; level < 10; level++) {
    const n = w.length;
    const k = w.map((m) => [...m.values()].reduce((a, b) => a + b, 0));
    const m2 = k.reduce((a, b) => a + b, 0);
    if (!m2) break;
    const comm = [...Array(n).keys()];
    const tot = [...k];
    let moved = true;
    for (let pass = 0; moved && pass < 20; pass++) {
      moved = false;
      for (let i = 0; i < n; i++) {
        const ci = comm[i]!;
        tot[ci]! -= k[i]!;
        const links = new Map<number, number>();
        for (const [j, wt] of w[i]!) if (j !== i) links.set(comm[j]!, (links.get(comm[j]!) ?? 0) + wt);
        let best = ci;
        let gain = (links.get(ci) ?? 0) - (tot[ci]! * k[i]!) / m2;
        for (const [c, wt] of [...links].sort((a, b) => a[0] - b[0])) {
          const g = wt - (tot[c]! * k[i]!) / m2;
          if (g > gain + 1e-12) [best, gain] = [c, g];
        }
        comm[i] = best;
        tot[best]! += k[i]!;
        if (best !== ci) moved = true;
      }
    }
    const ids2 = [...new Set(comm)];
    if (ids2.length === n) break;
    const renum = new Map(ids2.map((c, i) => [c, i] as const));
    of = of.map((node) => renum.get(comm[node]!)!);
    const next: Map<number, number>[] = ids2.map(() => new Map());
    for (let i = 0; i < n; i++)
      for (const [j, wt] of w[i]!) {
        const a = renum.get(comm[i]!)!;
        const b = renum.get(comm[j]!)!;
        next[a]!.set(b, (next[a]!.get(b) ?? 0) + wt);
      }
    w = next;
  }
  // number the groups from the largest down (ties by their first page)
  const size = new Map<number, number>();
  for (const c of of) size.set(c, (size.get(c) ?? 0) + 1);
  const firstAt = new Map<number, number>();
  of.forEach((c, i) => firstAt.has(c) || firstAt.set(c, i));
  const rank = new Map([...size.keys()].sort((a, b) => size.get(b)! - size.get(a)! || firstAt.get(a)! - firstAt.get(b)!).map((c, i) => [c, i] as const));
  return new Map(all.map((id, i) => [id, rank.get(of[i]!)!]));
}
