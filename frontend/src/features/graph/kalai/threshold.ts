import type { GraphModel } from "../types";
import { pageGraph, rng, themesOf, UnionFind } from "./core";
import { pageThemes } from "./fourier";

/**
 * Sharp thresholds (Friedgut–Kalai): keep each link with probability p and watch a monotone property
 * switch on. "Some page of A touches some page of B" is useless here (it holds at p ~ 0.03 for every
 * pair), so the property is *integration*: one connected piece holds at least `share` of theme A's pages
 * and `share` of theme B's (for A = B: the theme is *cohesive*).
 *
 * All links share one coupling: link e carries a uniform u_e and is kept at p iff its critical value
 * c_e < p (c_e = u_e, or 1-(1-u_e)^(1/w) when a link backed by w shared sources counts as w independent
 * strands). One Kruskal pass in c order gives, for one draw, the p at which every pair first holds; over
 * many draws, the share of draws holding at p is the threshold curve of that pair:
 *   - p50: where it holds half the time; low = the themes are woven together by many routes
 *   - width p90 - p10: narrow = a sharp, collective transition; wide = it hinges on a few bridges
 */

export interface ThresholdOptions {
  draws?: number;
  weighted?: boolean;
  hubs?: boolean;
  infer?: boolean;
  /** share of each theme's pages that must sit in one piece (default 0.5) */
  share?: number;
  seed?: number;
}

export interface PairThreshold {
  a: string;
  /** equal to `a` for a theme's own cohesion */
  b: string;
  /** sorted critical p over the draws (Infinity = never held) */
  crit: number[];
  p10: number;
  p50: number;
  p90: number;
  width: number;
  /** the link whose addition made the property hold in draw 0 (the pivotal bridge of that draw) */
  bridge: [string, string] | null;
}

export interface ThresholdResult {
  themes: string[];
  /** pairs a < b, then each theme's cohesion (a = b) */
  pairs: PairThreshold[];
  /** largest piece's share of pages at p (grid 0..1 step 0.02), averaged over draws */
  giant: { p: number; share: number }[];
  /** critical value of every link in draw 0, keyed by linkKey: the slider replays draw 0 */
  linkCrit: Map<string, number>;
  pageCount: number;
}

export const linkKey = (a: string, b: string): string => (a < b ? `${a}|${b}` : `${b}|${a}`);

const quantile = (s: readonly number[], q: number) => s[Math.min(s.length - 1, Math.floor(q * s.length))] as number;
const GRID = Array.from({ length: 51 }, (_, i) => i / 50);

export function thresholds(model: GraphModel, opts: ThresholdOptions = {}): ThresholdResult {
  const draws = opts.draws ?? 120;
  const share = opts.share ?? 0.5;
  const g = pageGraph(model, { hubs: opts.hubs });
  const allThemes = themesOf(model.nodes);
  const { themesOf: tags } = pageThemes(model, allThemes, opts);
  const n = g.ids.length;
  const memberOf: number[][] = g.ids.map((id) => (tags.get(id) ?? []).map((t) => allThemes.indexOf(t)));
  const size = allThemes.map((_, t) => memberOf.filter((m) => m.includes(t)).length);
  const live = allThemes.map((_, t) => t).filter((t) => (size[t] as number) >= 2);
  const themes = live.map((t) => allThemes[t] as string);
  const T = allThemes.length;
  const need = size.map((s) => Math.max(2, Math.ceil(s * share)));
  // pair (i, j), i < j over live themes, then each theme's cohesion (t, t)
  const keys: [number, number][] = [];
  for (let x = 0; x < live.length; x++) for (let y = x + 1; y < live.length; y++) keys.push([live[x] as number, live[y] as number]);
  for (const t of live) keys.push([t, t]);
  const keyIndex = new Map(keys.map(([i, j], k) => [i * T + j, k]));
  const crit: number[][] = keys.map(() => []);
  const bridge: ([string, string] | null)[] = keys.map(() => null);
  const giant = new Float64Array(GRID.length);
  const linkCrit = new Map<string, number>();
  const rand = rng(opts.seed ?? 11);

  for (let d = 0; d < draws; d++) {
    const order = g.edges.map((e) => {
      const u = rand();
      return { e, c: opts.weighted ? 1 - (1 - u) ** (1 / e.w) : u };
    });
    order.sort((x, y) => x.c - y.c);
    if (d === 0) for (const { e, c } of order) linkCrit.set(linkKey(g.ids[e.a] as string, g.ids[e.b] as string), c);
    const uf = new UnionFind(n);
    // per piece: how many pages of each theme it holds (only roots are read)
    const count: Int32Array[] = memberOf.map((m) => {
      const c = new Int32Array(T);
      for (const t of m) c[t] = 1;
      return c;
    });
    const held = new Float64Array(keys.length).fill(Infinity);
    let biggest = 1;
    let gi = 0;
    for (const { e, c } of order) {
      while (gi < GRID.length && (GRID[gi] as number) <= c) {
        giant[gi] = (giant[gi] as number) + biggest / n / draws;
        gi++;
      }
      const ra = uf.find(e.a);
      const rb = uf.find(e.b);
      if (ra === rb) continue;
      const r = uf.union(ra, rb);
      const into = count[r] as Int32Array;
      const from = count[r === ra ? rb : ra] as Int32Array;
      for (let t = 0; t < T; t++) into[t] = (into[t] as number) + (from[t] as number);
      const full = live.filter((t) => (into[t] as number) >= (need[t] as number));
      for (let x = 0; x < full.length; x++)
        for (let y = x; y < full.length; y++) {
          const k = keyIndex.get((full[x] as number) * T + (full[y] as number)) as number;
          if (held[k] === Infinity) {
            held[k] = c;
            if (d === 0) bridge[k] = [g.ids[e.a] as string, g.ids[e.b] as string];
          }
        }
      biggest = Math.max(biggest, uf.size[r] as number);
    }
    while (gi < GRID.length) {
        giant[gi] = (giant[gi] as number) + biggest / n / draws;
        gi++;
      }
    held.forEach((v, k) => (crit[k] as number[]).push(v));
  }

  const pairs: PairThreshold[] = keys.map(([i, j], k) => {
    const s = (crit[k] as number[]).sort((x, y) => x - y);
    const p10 = quantile(s, 0.1);
    const p50 = quantile(s, 0.5);
    const p90 = quantile(s, 0.9);
    return { a: allThemes[i] as string, b: allThemes[j] as string, crit: s, p10, p50, p90, width: p90 - p10, bridge: bridge[k] ?? null };
  });
  return { themes, pairs, giant: GRID.map((p, i) => ({ p, share: giant[i] as number })), linkCrit, pageCount: n };
}

/** Share of draws in which the property holds at p (the threshold curve). */
export const heldAt = (pt: PairThreshold, p: number): number => {
  let lo = 0;
  let hi = pt.crit.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((pt.crit[mid] as number) <= p) lo = mid + 1;
    else hi = mid;
  }
  return pt.crit.length ? lo / pt.crit.length : 0;
};
