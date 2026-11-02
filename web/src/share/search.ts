/**
 * Full-text search and shortest paths over the baked blob. A straight port of the two server-side
 * computations in src/kb_distillery/services/pages.py (search, find_paths), run in the browser on the share build's data.
 * search.test.ts pins the behaviour on a fixture.
 */
import type { PageDetail, PathResult, SearchHit, SearchResult } from "@/api/types";
import { PAGE_LINK, WIKILINK } from "@/lib/links";
import type { ShareBlob } from "./blob";

const MAX_PATHS = 4;

type Pages = Record<string, PageDetail>;

function titleOf(pages: Pages, slug: string): string {
  return pages[slug]?.card?.title || slug;
}

function plain(pages: Pages, s: string): string {
  s = s.replace(PAGE_LINK, (_m, label: string, slug: string) => {
    const text = label.replace(/\\(.)/g, "$1");
    return text === slug ? titleOf(pages, slug) : text;       // text equal to the slug chose no text: the page title
  });
  s = s.replace(WIKILINK, (_m, slug: string, label?: string) => (label || titleOf(pages, slug.trim()) || slug).trim());
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  s = s.replace(/[*_`>#]+/g, "");
  return s.replace(/\s+/g, " ").trim();
}

function clip(s: string, centre: number, width = 220): string {
  if (s.length <= width) return s;
  let start = Math.max(0, centre - Math.floor(width / 2));
  const end = Math.min(s.length, start + width);
  start = Math.max(0, end - width);
  let out = s.slice(start, end);
  if (start > 0) out = "…" + out.replace(/^\s+/, "");
  if (end < s.length) out = out.replace(/\s+$/, "") + "…";
  return out;
}

function count(hay: string, needle: string): number {
  if (!needle) return 0;
  let n = 0;
  let i = 0;
  while ((i = hay.indexOf(needle, i)) !== -1) {
    n += 1;
    i += needle.length;
  }
  return n;
}

export function searchPages(blob: Pick<ShareBlob, "pages">, query: string, limit?: number): SearchResult {
  const cap = Math.min(limit || 40, 5000);
  const q = (query || "").trim().toLowerCase();
  if (q.length < 2) return { query, total: 0, hits: [], related: [] };
  const pages = blob.pages;
  const terms = q.split(/\s+/).filter(Boolean);
  const hits: SearchHit[] = [];
  for (const slug of Object.keys(pages)) {
    const page = pages[slug]!;
    const title = page.card.title;
    const body = page.markdown || "";
    const lowTitle = title.toLowerCase();
    const lowBody = body.toLowerCase();
    const lowSlug = slug.toLowerCase();
    if (!terms.every((t) => lowTitle.includes(t) || lowBody.includes(t) || lowSlug.includes(t))) continue;
    let score = 0;
    for (const t of terms) {
      if (lowTitle.includes(t) || lowSlug.includes(t)) score += 50;
      score += Math.min(count(lowBody, t), 12);
    }
    if (lowTitle.includes(q)) score += 40;
    let snippet = "";
    for (const line of body.split("\n")) {
      const low = line.toLowerCase();
      if (terms.some((t) => low.includes(t)) && !/^\s*[#|]/.test(line)) {
        const p = plain(pages, line);
        const lp = p.toLowerCase();
        const positions = terms.filter((t) => lp.includes(t)).map((t) => lp.indexOf(t));
        snippet = clip(p, positions.length ? Math.min(...positions) : 0, 240);
        break;
      }
    }
    hits.push({ id: slug, title, type: page.card.type || "unknown", depth: page.card.depth || "", snippet: snippet || page.card.preview || "", score });
  }
  hits.sort((a, b) => b.score - a.score || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return { query, total: hits.length, hits: hits.slice(0, cap), related: [] };   // related comes from the local qmd service only
}

interface Adjacency {
  out: Record<string, Set<string>>;
  inn: Record<string, Set<string>>;
}

const adjacencyCache = new WeakMap<object, Adjacency>();

function adjacency(blob: Pick<ShareBlob, "pages" | "index">): Adjacency {
  const hit = adjacencyCache.get(blob);
  if (hit) return hit;
  const out: Record<string, Set<string>> = {};
  const inn: Record<string, Set<string>> = {};
  for (const slug of Object.keys(blob.pages)) {
    out[slug] = new Set();
    inn[slug] = new Set();
  }
  for (const [s, t] of blob.index.links as [string, string][]) {
    if (out[s] && inn[t]) {
      out[s]!.add(t);
      inn[t]!.add(s);
    }
  }
  const adj = { out, inn };
  adjacencyCache.set(blob, adj);
  return adj;
}

/** The context sentence of the link `from -> to`, recorded at build time as a backlink of `to`. */
function linkContext(pages: Pages, from: string, to: string): string {
  for (const b of pages[to]?.backlinks ?? []) if (b.id === from) return b.context || "";
  return "";
}

/** Shortest undirected link paths (at most four); null when either page is unknown. */
export function findPaths(blob: Pick<ShareBlob, "pages" | "index">, a: string, b: string): PathResult | null {
  if (!blob.pages[a] || !blob.pages[b]) return null;
  const { out, inn } = adjacency(blob);
  const nbrs = (s: string) => Array.from(new Set([...(out[s] ?? []), ...(inn[s] ?? [])])).sort();
  const dist: Record<string, number> = { [a]: 0 };
  const parents: Record<string, string[]> = { [a]: [] };
  const queue = [a];
  while (queue.length) {
    const cur = queue.shift()!;
    if (cur === b) break;
    for (const n of nbrs(cur)) {
      if (!(n in dist)) {
        dist[n] = dist[cur]! + 1;
        parents[n] = [cur];
        queue.push(n);
      } else if (dist[n] === dist[cur]! + 1) parents[n]!.push(cur);
    }
  }
  if (!(b in dist)) return { a, b, distance: null, paths: [] };
  const paths: string[][] = [];
  (function walk(node: string, tail: string[]) {
    if (paths.length >= MAX_PATHS) return;
    if (node === a) {
      paths.push([a, ...tail]);
      return;
    }
    for (const p of parents[node]!) walk(p, [node, ...tail]);
  })(b, []);
  const hop = (s: string, t: string) =>
    out[s]!.has(t)
      ? { from: s, to: t, dir: "forward", context: linkContext(blob.pages, s, t) }
      : { from: s, to: t, dir: "back", context: linkContext(blob.pages, t, s) };
  return {
    a,
    b,
    distance: dist[b]!,
    paths: paths.map((p) => ({ nodes: p, hops: p.slice(0, -1).map((s, i) => hop(s, p[i + 1]!)) })),
  };
}
