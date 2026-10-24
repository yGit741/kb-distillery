import type { GNode, GraphModel } from "../types";
import { isHub, rng, themesOf } from "./core";

/**
 * The Fourier spectrum of the vault. Every themed page is a point x in {0,1}^k (one bit per theme). We
 * expand in the p-biased characters phi_S(x) = prod_{i in S} (x_i - p_i) / sigma_i, so the spectrum
 * measures structure *beyond* how common each theme is:
 *   - a level-2 coefficient is the correlation of two themes (do my pages treat them together?)
 *   - level-k energy sum_{|S|=k} E[phi_S]^2, against a shuffled null that keeps every theme's
 *     frequency but kills interactions, says how much of the vault is pairs, triples, ...
 *   - for a yes/no "attention" signal f (did I read the page deeply?), f^(S) = E[f phi_S] says which
 *     themes and pairs predict where my attention goes.
 */

export type AttentionTarget = "deep" | "digested";

export interface PairStat {
  a: string;
  b: string;
  both: number;
  expected: number;
  /** the level-2 p-biased coefficient (= correlation of the two theme bits) */
  coef: number;
}

/** Three themes that meet pairwise but (almost) never all together: a hole in the theme complex. */
export interface Hole {
  themes: [string, string, string];
  /** pages carrying all three */
  all: number;
  /** pages per pair (ab, bc, ac) */
  pairs: [number, number, number];
  /** Kirkwood estimate from the pairs alone: n * p_ab p_bc p_ac / (p_a p_b p_c) */
  expected: number;
}

export interface LevelEnergy {
  level: number;
  observed: number;
  /** mean energy over shuffled vaults (same theme frequencies, no interactions) */
  null: number;
}

export interface AttentionCoef {
  set: string[];
  coef: number;
  /** pages carrying every theme in the set */
  support: number;
  /** share of those pages that hit the target */
  rate: number;
}

export interface Spectrum {
  themes: string[];
  n: number;
  untagged: number;
  inferred: number;
  prevalence: number[];
  pairs: PairStat[];
  levels: LevelEnergy[];
  attention: AttentionCoef[];
  attentionRate: number;
  holes: Hole[];
  /** themed pages per theme id, to light them on the graph */
  members: Map<string, string[]>;
}

export interface SpectrumOptions {
  hubs?: boolean;
  /** give an untagged page the themes most of its tagged neighbours share */
  infer?: boolean;
  target?: AttentionTarget;
  nullRuns?: number;
  minSupport?: number;
  seed?: number;
}

const hits = (n: GNode, t: AttentionTarget) =>
  t === "deep" ? n.depth === "full" || n.depth === "deep" : n.layer === "concept" || (n.depth !== undefined && n.depth !== null && n.depth !== "listed");

/** Themes of each page, optionally inferring them for untagged pages from their neighbours. */
export function pageThemes(model: GraphModel, themes: readonly string[], opts: { hubs?: boolean; infer?: boolean } = {}) {
  const allowed = new Set(themes);
  const own = new Map<string, string[]>();
  for (const n of model.nodes) {
    if (!opts.hubs && isHub(n)) continue;
    own.set(n.id, n.areas.filter((a) => allowed.has(a)));
  }
  let inferred = 0;
  if (opts.infer) {
    const nb = new Map<string, string[]>();
    const add = (a: string, b: string) => {
      if (!nb.has(a)) nb.set(a, []);
      nb.get(a)?.push(b);
    };
    for (const l of model.links) {
      add(l.source, l.target);
      add(l.target, l.source);
    }
    const out = new Map(own);
    for (const [id, ts] of own) {
      if (ts.length) continue;
      const tagged = (nb.get(id) ?? []).map((j) => own.get(j) ?? []).filter((t) => t.length);
      if (tagged.length < 2) continue;
      const count = new Map<string, number>();
      for (const t of tagged) for (const a of t) count.set(a, (count.get(a) ?? 0) + 1);
      const got = [...count].filter(([, c]) => c * 2 >= tagged.length).map(([a]) => a);
      if (got.length) {
        out.set(id, got);
        inferred++;
      }
    }
    return { themesOf: out, inferred };
  }
  return { themesOf: own, inferred };
}

function* subsets(k: number, size: number, start = 0, acc: number[] = []): Generator<number[]> {
  if (acc.length === size) {
    yield acc.slice();
    return;
  }
  for (let i = start; i < k; i++) {
    acc.push(i);
    yield* subsets(k, size, i + 1, acc);
    acc.pop();
  }
}

/** sum over |S| = level of E[phi_S]^2, on standardised theme columns z[i][page]. */
function energy(z: Float64Array[], n: number, level: number): number {
  let e = 0;
  for (const S of subsets(z.length, level)) {
    let s = 0;
    for (let p = 0; p < n; p++) {
      let prod = 1;
      for (const i of S) prod *= (z[i] as Float64Array)[p] as number;
      s += prod;
    }
    e += (s / n) ** 2;
  }
  return e;
}

export function spectrum(model: GraphModel, opts: SpectrumOptions = {}): Spectrum {
  const target = opts.target ?? "deep";
  const minSupport = opts.minSupport ?? 5;
  const all = themesOf(model.nodes);
  const { themesOf: tagsOf, inferred } = pageThemes(model, all, opts);
  const byId = new Map(model.nodes.map((n) => [n.id, n]));
  const pages = [...tagsOf].filter(([, t]) => t.length).map(([id, t]) => ({ id, t: new Set(t) }));
  const untagged = tagsOf.size - pages.length;
  const n = pages.length;
  const x = all.map((th) => pages.map((p) => (p.t.has(th) ? 1 : 0)));
  const prevalence = x.map((col) => (n ? col.reduce<number>((s, v) => s + v, 0) / n : 0));
  // only themes that vary carry information (sigma > 0)
  const live = all.map((_, i) => i).filter((i) => (prevalence[i] as number) > 0 && (prevalence[i] as number) < 1);
  const themes = live.map((i) => all[i] as string);
  const p = live.map((i) => prevalence[i] as number);
  const z = live.map((i, c) => {
    const pi = p[c] as number;
    const sd = Math.sqrt(pi * (1 - pi));
    return Float64Array.from(x[i] as number[], (v) => (v - pi) / sd);
  });
  const members = new Map(themes.map((th) => [th, pages.filter((pg) => pg.t.has(th)).map((pg) => pg.id)]));

  const pairs: PairStat[] = [];
  for (let i = 0; i < themes.length; i++)
    for (let j = i + 1; j < themes.length; j++) {
      let both = 0;
      let s = 0;
      for (let q = 0; q < n; q++) {
        s += ((z[i] as Float64Array)[q] as number) * ((z[j] as Float64Array)[q] as number);
        if (pages[q]?.t.has(themes[i] as string) && pages[q]?.t.has(themes[j] as string)) both++;
      }
      pairs.push({ a: themes[i] as string, b: themes[j] as string, both, expected: (p[i] as number) * (p[j] as number) * n, coef: n ? s / n : 0 });
    }

  const rand = rng(opts.seed ?? 7);
  const runs = opts.nullRuns ?? 12;
  const levels: LevelEnergy[] = [2, 3].map((level) => ({ level, observed: n ? energy(z, n, level) : 0, null: 0 }));
  for (let r = 0; r < runs && n; r++) {
    const shuffled = z.map((col) => {
      const c = Float64Array.from(col);
      for (let i = c.length - 1; i > 0; i--) {
        const j = Math.floor(rand() * (i + 1));
        [c[i], c[j]] = [c[j] as number, c[i] as number];
      }
      return c;
    });
    for (const L of levels) L.null += energy(shuffled, n, L.level) / runs;
  }

  const f = pages.map((pg) => (hits(byId.get(pg.id) as GNode, target) ? 1 : -1));
  const attentionRate = n ? f.filter((v) => v > 0).length / n : 0;
  const attention: AttentionCoef[] = [];
  for (const size of [1, 2])
    for (const S of subsets(themes.length, size)) {
      let support = 0;
      let hit = 0;
      let s = 0;
      for (let q = 0; q < n; q++) {
        let prod = f[q] as number;
        let inAll = true;
        for (const i of S) {
          prod *= (z[i] as Float64Array)[q] as number;
          if (!pages[q]?.t.has(themes[i] as string)) inAll = false;
        }
        s += prod;
        if (inAll) {
          support++;
          if ((f[q] as number) > 0) hit++;
        }
      }
      if (support < minSupport) continue;
      attention.push({ set: S.map((i) => themes[i] as string), coef: s / n, support, rate: hit / support });
    }
  attention.sort((a, b) => Math.abs(b.coef) - Math.abs(a.coef));
  const pairCount = new Map(pairs.map((q) => [`${q.a}|${q.b}`, q.both]));
  const holes: Hole[] = [];
  for (const [i, j, k] of subsets(themes.length, 3) as Generator<[number, number, number]>) {
    const [a, b, c] = [themes[i], themes[j], themes[k]] as [string, string, string];
    const ab = pairCount.get(`${a}|${b}`) ?? 0;
    const bc = pairCount.get(`${b}|${c}`) ?? 0;
    const ac = pairCount.get(`${a}|${c}`) ?? 0;
    if (ab < 2 || bc < 2 || ac < 2) continue;
    const expected = (n * (ab / n) * (bc / n) * (ac / n)) / ((p[i] as number) * (p[j] as number) * (p[k] as number));
    const all = pages.filter((pg) => pg.t.has(a) && pg.t.has(b) && pg.t.has(c)).length;
    if (expected >= 1 && all <= expected / 3) holes.push({ themes: [a, b, c], all, pairs: [ab, bc, ac], expected });
  }
  holes.sort((x, y) => y.expected - y.all - (x.expected - x.all));
  return { themes, n, untagged, inferred, prevalence: p, pairs, levels, attention, attentionRate, holes, members };
}

/** Pairs worth a look: over-represented intersections and the big pairs that (almost) never meet. */
export function notablePairs(s: Spectrum, k = 5) {
  const sorted = [...s.pairs].sort((a, b) => b.coef - a.coef);
  const over = sorted.filter((p) => p.coef > 0 && p.both >= 2).slice(0, k);
  const gaps = [...s.pairs].filter((p) => p.expected >= 3 && p.both < p.expected / 2).sort((a, b) => b.expected - b.both - (a.expected - a.both)).slice(0, k);
  return { over, gaps };
}
