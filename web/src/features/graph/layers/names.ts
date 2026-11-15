import { findPages } from "../pageSearch";
import type { GNode } from "../types";
import { FAVORITES, FOCUS, type EdgeCond, type Layer, type NodeCond } from "./model";

/** A name that did not resolve to exactly one page: the pages it might mean (none when it matches nothing). */
export interface Ambiguity {
  name: string;
  options: { slug: string; title: string }[];
}

export interface Resolved {
  /** The layers with every resolved name replaced by its page's slug; unresolved names stay as typed. */
  layers: Layer[];
  ambiguous: Ambiguity[];
}

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");
const aliasesOf = (n: GNode): string[] => (n.properties?.aliases ?? n.properties?.alias ?? "").split(/[,;|]/).map(norm).filter(Boolean);
const names = (n: GNode): string[] => [norm(n.title || ""), norm(n.label || ""), n.id.toLowerCase(), ...aliasesOf(n)].filter(Boolean);
const option = (n: GNode) => ({ slug: n.id, title: n.title || n.id });

/** One name: a slug, or the options it leaves open. Exact (title, slug or alias) wins, then a unique title prefix.
 * `slugFirst`: a page's own slug wins before that (a resolved line prints slugs where titles are shared). */
export function resolveName(name: string, nodes: readonly GNode[], slugFirst = false): { slug: string } | Ambiguity {
  const own = slugFirst ? nodes.find((n) => n.id === name.trim()) : undefined;
  if (own) return { slug: own.id };
  const q = norm(name);
  const slugForm = q.replace(/ /g, "-");
  const exact = nodes.filter((n) => names(n).some((x) => x === q || x === slugForm));
  if (exact.length === 1) return { slug: exact[0]!.id };
  if (exact.length > 1) return { name, options: exact.slice(0, 8).map(option) };
  const prefix = nodes.filter((n) => names(n).some((x) => x.startsWith(q)));
  if (prefix.length === 1) return { slug: prefix[0]!.id };
  if (prefix.length > 1) return { name, options: prefix.sort((a, b) => (b.inDegree || 0) - (a.inDegree || 0)).slice(0, 8).map(option) };
  return { name, options: findPages(nodes, name, 6).map(option) };
}

const isWord = (s: string) => s === FAVORITES || s === FOCUS;

/**
 * Maps every quoted name in the layers to a slug. `focus` fills the `$focus` placeholder (left alone when absent);
 * `chosen` holds names the user already picked from a "did you mean" list.
 */
export function resolveNames(layers: Layer[], nodes: readonly GNode[], opts: { focus?: string; chosen?: Readonly<Record<string, string>>; slugFirst?: boolean } = {}): Resolved {
  const ambiguous: Ambiguity[] = [];
  const cache = new Map<string, string>();
  const one = (name: string): string => {
    if (name === FOCUS) return opts.focus ?? name;
    if (isWord(name)) return name;
    const picked = opts.chosen?.[name];
    if (picked) return picked;
    const hit = cache.get(name);
    if (hit) return hit;
    const r = resolveName(name, nodes, opts.slugFirst);
    if ("slug" in r) {
      cache.set(name, r.slug);
      return r.slug;
    }
    if (!ambiguous.some((a) => a.name === name)) ambiguous.push(r);
    return name;
  };
  const node = (c: NodeCond): NodeCond => {
    switch (c.t) {
      case "hops":
        return { ...c, of: one(c.of) };
      case "paths":
      case "shortest":
      case "common":
        return { ...c, a: one(c.a), b: one(c.b) };
      case "component":
      case "community":
        return c.of ? { ...c, of: one(c.of) } : c;
      case "name":
        return { ...c, slugs: c.slugs.map(one) };
      case "about":
        return c.phrase === FOCUS && opts.focus ? { ...c, phrase: nodes.find((n) => n.id === opts.focus)?.title || opts.focus, slug: opts.focus } : c;
      case "not":
        return { ...c, cond: node(c.cond) };
      default:
        return c;
    }
  };
  const edge = (c: EdgeCond): EdgeCond => (c.t === "endpoints" ? { ...c, slugs: c.slugs.map(one) } : c);
  const out = layers.map((l) => ({
    ...l,
    subgraph: { ...(l.subgraph.nodes && { nodes: l.subgraph.nodes.map(node) }), ...(l.subgraph.edges && { edges: l.subgraph.edges.map(edge) }) },
  }));
  return { layers: out, ambiguous };
}

/** Titles (lower case) that name one page only: no other page has it as its title, slug or alias. A line can name a
 * page by such a title and read back to the same page without a "did you mean". */
export function uniqueTitles(nodes: readonly GNode[]): Set<string> {
  const owners = new Map<string, number>();
  for (const n of nodes) for (const x of new Set(names(n))) owners.set(x, (owners.get(x) ?? 0) + 1);
  const out = new Set<string>();
  for (const n of nodes) {
    const t = norm(n.title || "");
    // the title's slug form ("learning-theory") is read as a name too: no other page may own it
    const sf = t.replace(/ /g, "-");
    if (t && owners.get(t) === 1 && (owners.get(sf) ?? 0) - (names(n).includes(sf) ? 1 : 0) === 0) out.add(t);
  }
  return out;
}

/** How a page is written in a line: its quoted title when that title names it alone, else its quoted slug. */
export function nameFor(n: GNode, unique: ReadonlySet<string>): string {
  const t = (n.title || "").trim();
  return `"${t && !/["\\]/.test(t) && unique.has(norm(t)) ? t : n.id}"`;
}

/** A resolved line as people read it: each quoted slug of a page becomes that page's title (when the title is its
 * own), so `shortest path between "learning-theory" and "juntas"` reads `... between "Learning theory" and "Juntas"`.
 * The line still reads back to the same pages: a title resolves like the slug did. */
export function readableLine(line: string, byId: ReadonlyMap<string, GNode>, unique: ReadonlySet<string>): string {
  return line.replace(/"((?:[^"\\]|\\.)*)"/g, (whole, inner: string) => {
    const n = byId.get(inner.replace(/\\(.)/g, "$1"));
    return n ? nameFor(n, unique) : whole;
  });
}
