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

/** One name: a slug, or the options it leaves open. Exact (title, slug or alias) wins, then a unique title prefix. */
export function resolveName(name: string, nodes: readonly GNode[]): { slug: string } | Ambiguity {
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
export function resolveNames(layers: Layer[], nodes: readonly GNode[], opts: { focus?: string; chosen?: Readonly<Record<string, string>> } = {}): Resolved {
  const ambiguous: Ambiguity[] = [];
  const cache = new Map<string, string>();
  const one = (name: string): string => {
    if (name === FOCUS) return opts.focus ?? name;
    if (isWord(name)) return name;
    const picked = opts.chosen?.[name];
    if (picked) return picked;
    const hit = cache.get(name);
    if (hit) return hit;
    const r = resolveName(name, nodes);
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
        return { ...c, a: one(c.a), b: one(c.b) };
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
