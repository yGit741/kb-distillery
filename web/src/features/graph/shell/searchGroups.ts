import type { GNode } from "../types";

/**
 * Tier 1 of the search line (flag graph-intent): an in-memory index of titles, aliases, types, tags, pinned view names
 * and command labels, built once per graph load and matched on every keystroke. Pure, no React.
 */

export type GroupId = "pages" | "think" | "sets" | "views" | "commands" | "related" | "ask";
/** The fixed order of the groups. "related" and "ask" are filled by the server tiers; empty ones render nothing. */
export const GROUP_IDS: readonly GroupId[] = ["pages", "think", "sets", "views", "commands", "related", "ask"];

/** What a row's action menu acts on: one page, or a set of pages. */
export type RowTarget = { kind: "node"; node: GNode } | { kind: "set"; ids: string[]; label: string };

interface Entry {
  node: GNode;
  title: string;
  slug: string;
  aliases: string[];
  /** title, aliases and tags, lower case: what a set counts. */
  hay: string;
  think: boolean;
}
interface Named {
  id: string;
  name: string;
  lower: string;
}
export interface SearchIndex {
  entries: readonly Entry[];
  views: readonly Named[];
  commands: readonly Named[];
}

const list = (v: string | undefined) => (v ?? "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);

/** Think notes are the pages of the think layer. */
export const isThink = (n: Pick<GNode, "type" | "layer">): boolean => /think/i.test(n.type) || /think/i.test(n.layer);

/** The page part of the index: built once per graph load. */
export function buildSearchIndex(nodes: readonly GNode[]): SearchIndex {
  const entries = nodes.map<Entry>((node) => {
    const title = (node.title || "").toLowerCase();
    const aliases = list(node.properties?.aliases);
    const tags = list(node.properties?.tags);
    return { node, title, slug: node.id.toLowerCase(), aliases, hay: [title, ...aliases, ...tags].join(" \n"), think: isThink(node) };
  });
  return { entries, views: [], commands: [] };
}

/** The same page entries with the pinned view names and command labels (small lists, cheap to redo). */
export function withNames(base: SearchIndex, views: readonly { id: string; name: string }[], commands: readonly { id: string; label: string }[]): SearchIndex {
  return {
    entries: base.entries,
    views: views.map((v) => ({ id: v.id, name: v.name, lower: v.name.toLowerCase() })),
    commands: commands.map((c) => ({ id: c.id, name: c.label, lower: c.label.toLowerCase() })),
  };
}

function ladder(t: string, q: string): number {
  if (t === q) return 100;
  if (t.startsWith(q)) return 80;
  if (t.includes(` ${q}`)) return 62;
  if (t.includes(q)) return 50;
  return 0;
}

function score(e: Entry, q: string, terms: string[], slugQ: string): number {
  let s = ladder(e.title, q);
  for (const a of e.aliases) s = Math.max(s, ladder(a, q) - 5);
  if (s) return s;
  if (e.slug.includes(slugQ)) return 40;
  return terms.length > 1 && terms.every((x) => e.title.includes(x) || e.slug.includes(x)) ? 30 : 0;
}

/** Keep the `cap` best of a stream without sorting all of it: a short list kept in order. */
function keepBest<T>(top: [number, T][], cap: number, s: number, v: T) {
  if (top.length >= cap && s <= top[top.length - 1]![0]) return;
  let i = top.length;
  while (i > 0 && top[i - 1]![0] < s) i--;
  top.splice(i, 0, [s, v]);
  if (top.length > cap) top.pop();
}

export interface Tier1 {
  pages: GNode[];
  think: GNode[];
  /** Pages whose title, alias or tags hold every word; null under two pages or two letters. */
  set: { ids: string[] } | null;
  views: { id: string; name: string }[];
  commands: { id: string; name: string }[];
}

export const NO_HITS: Tier1 = { pages: [], think: [], set: null, views: [], commands: [] };

export function matchTier1(index: SearchIndex, raw: string, limits = { pages: 6, think: 4, views: 3, commands: 4 }): Tier1 {
  const q = raw.trim().toLowerCase();
  if (!q) return NO_HITS;
  const terms = q.split(/\s+/);
  const slugQ = q.replace(/\s+/g, "-");
  const topPages: [number, GNode][] = [];
  const topThink: [number, GNode][] = [];
  const set: string[] = [];
  const wantSet = q.length >= 2;
  for (const e of index.entries) {
    const s = score(e, q, terms, slugQ);
    if (s >= 30) {
      const w = s + Math.min(e.node.inDegree || 0, 20) / 10;
      if (e.think) keepBest(topThink, limits.think, w, e.node);
      else keepBest(topPages, limits.pages, w, e.node);
    }
    if (wantSet && terms.every((x) => e.hay.includes(x))) set.push(e.node.id);
  }
  const pages = topPages.map(([, n]) => n);
  const think = topThink.map(([, n]) => n);
  const all = (hay: string) => terms.every((x) => hay.includes(x));
  return {
    pages,
    think,
    set: set.length >= 2 ? { ids: set } : null,
    views: index.views.filter((v) => all(v.lower)).slice(0, limits.views).map((v) => ({ id: v.id, name: v.name })),
    commands: index.commands.filter((c) => all(c.lower)).slice(0, limits.commands).map((c) => ({ id: c.id, name: c.name })),
  };
}

/** How a page was found: by its title or alias, by its text, or by meaning. */
export type Via = "title" | "text" | "related";

export interface Candidate {
  group: GroupId;
  via: Via;
  node: GNode;
  snippet?: string;
  /** Meaning hits: how close, 0 to 100. */
  score?: number;
}
export interface Placed {
  node: GNode;
  snippet?: string;
  score?: number;
  via: Via;
  /** The other ways this page was also found (one small mark in the row). */
  also: Via[];
}

/** A page that would appear in two groups appears once, in the top one, marked with the other way. Candidates come in group order. */
export function placeOnce(cands: readonly Candidate[]): Record<GroupId, Placed[]> {
  const out: Record<GroupId, Placed[]> = { pages: [], think: [], sets: [], views: [], commands: [], related: [], ask: [] };
  const first = new Map<string, Placed>();
  for (const c of cands) {
    const seen = first.get(c.node.id);
    if (seen) {
      if (c.via !== seen.via && !seen.also.includes(c.via)) seen.also.push(c.via);
      continue;
    }
    const p: Placed = { node: c.node, snippet: c.snippet, score: c.score, via: c.via, also: [] };
    first.set(c.node.id, p);
    out[c.group].push(p);
  }
  return out;
}
