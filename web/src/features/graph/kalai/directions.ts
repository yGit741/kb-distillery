import type { GNode, GraphModel } from "../types";
import { notablePairs, pageThemes, type Spectrum } from "./fourier";

/**
 * Research directions: the spectrum's gaps (two big themes that rarely share a page) and holes (three
 * themes that meet only in pairs) turned into cards a thesis decision can start from. For each direction:
 * what already sits in the intersection, the open questions and ideas closest to every side, and how much
 * of each side I have actually read. Closeness of a page to a theme = share of the page and its neighbours
 * carrying that theme; a page is close to a direction by its *weakest* side, so only pages that reach every
 * side rank.
 */

export interface DirectionPage {
  id: string;
  /** min over sides of the page's closeness to that side (0..1) */
  reach: number;
}

export interface Side {
  theme: string;
  pages: number;
  /** pages of the theme read in depth (full or deep) */
  deep: number;
}

export interface Direction {
  id: string;
  kind: "gap" | "hole";
  sides: Side[];
  /** pages carrying every side now */
  existing: string[];
  /** pages expected in the intersection if the themes mixed as usual */
  expected: number;
  /** expected - existing: how much is missing */
  missing: number;
  questions: DirectionPage[];
  ideas: DirectionPage[];
  /** how much of my own thinking already reaches every side: the best reach among its questions and ideas */
  foothold: "strong" | "thin" | "none";
}

export const footholdOf = (reach: number): Direction["foothold"] => (reach >= 0.3 ? "strong" : reach >= 0.1 ? "thin" : "none");

const deepRead = (n: GNode | undefined) => n?.depth === "full" || n?.depth === "deep";

export function directions(model: GraphModel, s: Spectrum, opts: { perList?: number; gaps?: number } = {}): Direction[] {
  const perList = opts.perList ?? 3;
  const byId = new Map(model.nodes.map((n) => [n.id, n]));
  const { themesOf: tags } = pageThemes(model, s.themes, { hubs: true });
  const nb = new Map<string, Set<string>>();
  const add = (a: string, b: string) => {
    if (!nb.has(a)) nb.set(a, new Set());
    nb.get(a)?.add(b);
  };
  for (const l of model.links) {
    add(l.source, l.target);
    add(l.target, l.source);
  }
  for (const c of model.conceptLinks) {
    add(c.source, c.target);
    add(c.target, c.source);
  }
  const closeness = (id: string, theme: string) => {
    const around = [id, ...(nb.get(id) ?? [])].filter((x) => byId.get(x)?.type !== "topic");
    return around.filter((x) => (tags.get(x) ?? []).includes(theme)).length / around.length;
  };
  const side = (theme: string): Side => {
    const m = s.members.get(theme) ?? [];
    return { theme, pages: m.length, deep: m.filter((id) => deepRead(byId.get(id))).length };
  };
  const nearest = (themes: readonly string[], type: string): DirectionPage[] =>
    model.nodes
      .filter((n) => n.type === type)
      .map((n) => ({ id: n.id, reach: Math.min(...themes.map((t) => closeness(n.id, t))) }))
      .filter((p) => p.reach > 0)
      .sort((a, b) => b.reach - a.reach)
      .slice(0, perList);
  const build = (kind: Direction["kind"], themes: string[], expected: number): Direction => {
    const sets = themes.map((t) => new Set(s.members.get(t) ?? []));
    const existing = [...(sets[0] ?? [])].filter((id) => sets.every((x) => x.has(id)));
    const questions = nearest(themes, "question");
    const ideas = nearest(themes, "idea");
    return {
      id: `${kind}:${themes.join("+")}`,
      kind,
      sides: themes.map(side),
      existing,
      expected,
      missing: Math.max(0, expected - existing.length),
      questions,
      ideas,
      foothold: footholdOf(Math.max(0, ...questions.map((q) => q.reach), ...ideas.map((q) => q.reach))),
    };
  };
  const { gaps } = notablePairs(s, opts.gaps ?? 6);
  const out = [
    ...gaps.map((g) => build("gap", [g.a, g.b], g.expected)),
    ...s.holes.map((h) => build("hole", [...h.themes], h.expected)),
  ];
  return out.sort((a, b) => b.missing - a.missing);
}
