import type { GraphModel } from "../types";
import { breathe, pageGraph, rng, themesOf, UnionFind } from "./core";
import { pageThemes } from "./fourier";
import type { ThresholdResult } from "./threshold";

/**
 * Influence of a page (KKL): in a random kept graph at a theme's critical point p50, a page
 * is *pivotal* for that theme when the theme holds together with it and falls apart without it. Its
 * influence on the theme is the probability of being pivotal; its total influence is the sum over themes.
 * KKL says some coordinate always has influence at least ~ (log n)/n; a vault where one page carries a
 * theme is the extreme case, and that page is the one to strengthen (more links, more sources) first.
 */

export interface InfluenceOptions {
  draws?: number;
  share?: number;
  weighted?: boolean;
  hubs?: boolean;
  infer?: boolean;
  seed?: number;
}

export interface Influence {
  /** page id -> sum over themes of Pr[pivotal at that theme's p50] */
  total: Map<string, number>;
  /** theme -> its most influential pages, best first */
  perTheme: Map<string, { id: string; inf: number }[]>;
}

export async function influence(model: GraphModel, th: ThresholdResult, opts: InfluenceOptions = {}): Promise<Influence> {
  const draws = opts.draws ?? 8;
  const share = opts.share ?? 0.5;
  const g = pageGraph(model, { hubs: opts.hubs });
  const themes = themesOf(model.nodes);
  const { themesOf: tags } = pageThemes(model, themes, opts);
  const n = g.ids.length;
  const total = new Map<string, number>();
  const perTheme = new Map<string, { id: string; inf: number }[]>();
  const rand = rng(opts.seed ?? 23);

  for (const t of themes) {
    const own = th.pairs.find((x) => x.a === t && x.b === t);
    if (!own || !Number.isFinite(own.p50)) continue;
    const isMember = Uint8Array.from(g.ids, (id) => ((tags.get(id) ?? []).includes(t) ? 1 : 0));
    const size = isMember.reduce((s, v) => s + v, 0);
    const need = Math.max(2, Math.ceil(size * share));
    const pivotal = new Float64Array(n);
    const holds = (edges: readonly { a: number; b: number }[], skip: number) => {
      const uf = new UnionFind(n);
      for (const e of edges) if (e.a !== skip && e.b !== skip) uf.union(e.a, e.b);
      const count = new Map<number, number>();
      for (let i = 0; i < n; i++) {
        if (!isMember[i] || i === skip) continue;
        const r = uf.find(i);
        const c = (count.get(r) ?? 0) + 1;
        if (c >= need) return { ok: true as const, uf, root: r };
        count.set(r, c);
      }
      return { ok: false as const, uf, root: -1 };
    };
    for (let d = 0; d < draws; d++) {
      const kept = g.edges.filter((e) => {
        const u = rand();
        return (opts.weighted ? 1 - (1 - u) ** (1 / e.w) : u) < own.p50;
      });
      const base = holds(kept, -1);
      if (!base.ok) continue;
      // only pages inside the cohesive piece can break it; only its links matter
      const inPiece = new Set<number>();
      for (let i = 0; i < n; i++) if (base.uf.find(i) === base.root) inPiece.add(i);
      const local = kept.filter((e) => inPiece.has(e.a));
      for (const v of inPiece) if (!holds(local, v).ok) pivotal[v] = (pivotal[v] as number) + 1 / draws;
    }
    const ranked: { id: string; inf: number }[] = [];
    pivotal.forEach((p, i) => {
      if (!p) return;
      const id = g.ids[i] as string;
      total.set(id, (total.get(id) ?? 0) + p);
      ranked.push({ id, inf: p });
    });
    perTheme.set(t, ranked.sort((a, b) => b.inf - a.inf).slice(0, 5));
    await breathe();
  }
  return { total, perTheme };
}
