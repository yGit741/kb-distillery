/** Pure logic of the Pages screen: link graph, legacy-link redirects, trail and pins, markdown prep, ring layout. */
import { LAYER_TYPES, type Layer } from "@/api/model";
import type { PageCard, PageIndex } from "@/api/types";
import type { GNode } from "@/features/graph/types";

// ---------- data model ----------

export const layerOf = (type?: string | null): Layer | undefined =>
  (Object.keys(LAYER_TYPES) as Layer[]).find((l) => (LAYER_TYPES[l] as readonly string[]).includes(type ?? ""));

/** Frontmatter values arrive untyped; read them defensively. */
export const fmString = (fm: Record<string, unknown>, key: string): string => {
  const v = fm[key];
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  return "";
};
export const fmList = (fm: Record<string, unknown>, key: string): string[] => {
  const v = fm[key];
  if (Array.isArray(v)) return v.map(String).filter(Boolean);
  return typeof v === "string" && v ? [v] : [];
};

export const mtimeOf = (c: PageCard): number => {
  const m = c.mtime;
  const n = typeof m === "number" ? m : typeof m === "string" ? Number(m) : 0;
  return Number.isFinite(n) ? n : 0;
};

export const agoLabel = (ts: number, now = Date.now() / 1000): string => {
  if (!ts) return "";
  const d = Math.floor((now - ts) / 86400);
  if (d <= 0) return "today";
  if (d === 1) return "yesterday";
  if (d < 30) return `${d}d ago`;
  if (d < 365) return `${Math.floor(d / 30)}mo ago`;
  return `${Math.floor(d / 365)}y ago`;
};

// ---------- link graph ----------

export interface LinkGraph {
  byId: ReadonlyMap<string, PageCard>;
  out: ReadonlyMap<string, ReadonlySet<string>>;
  inn: ReadonlyMap<string, ReadonlySet<string>>;
}

export function buildGraph(index: PageIndex): LinkGraph {
  const byId = new Map<string, PageCard>();
  const out = new Map<string, Set<string>>();
  const inn = new Map<string, Set<string>>();
  for (const p of index.pages) {
    byId.set(p.id, p);
    out.set(p.id, new Set());
    inn.set(p.id, new Set());
  }
  for (const [s, t] of index.links) {
    if (s === undefined || t === undefined) continue;
    out.get(s)?.add(t);
    inn.get(t)?.add(s);
  }
  return { byId, out, inn };
}

export const neighbours = (g: LinkGraph, slug: string): Set<string> =>
  new Set([...(g.out.get(slug) ?? []), ...(g.inn.get(slug) ?? [])]);

export const degree = (g: LinkGraph, slug: string): number => neighbours(g, slug).size;

export const titleOf = (g: LinkGraph, slug: string): string => g.byId.get(slug)?.title || slug;

// ---------- legacy links ----------

export type LegacyTarget =
  | { kind: "page"; slug: string }
  | { kind: "search"; q: string }
  | { kind: "browse"; type: string }
  | { kind: "path"; a?: string; b?: string };

/** Old Explore deep links: `#/p/<slug>`, `#/search/<q>`, `#/browse/<type>`, `#/path/<a>/<b>`. */
export function parseLegacyHash(hash: string): LegacyTarget | null {
  const parts = hash
    .replace(/^#\/?/, "")
    .split("/")
    .map((s) => {
      try {
        return decodeURIComponent(s);
      } catch {
        return s;
      }
    });
  const [kind, a, b] = parts;
  if (kind === "p" && a) return { kind: "page", slug: a };
  if (kind === "search" && a) return { kind: "search", q: a };
  if (kind === "browse" && a) return { kind: "browse", type: a };
  if (kind === "path") return { kind: "path", a: a || undefined, b: b || undefined };
  return null;
}

// ---------- trail and pins (per-viewer convenience; keys kept from the legacy Explore) ----------

export const TRAIL_KEY = "explore-trail";
export const PINS_KEY = "explore-pins";
export const TRAIL_MAX = 14;

export function loadList(key: string): string[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}
export function saveList(key: string, list: readonly string[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(list));
  } catch {
    /* storage unavailable: the screen works without it */
  }
}
export const withTrail = (trail: readonly string[], slug: string): string[] =>
  [slug, ...trail.filter((s) => s !== slug)].slice(0, TRAIL_MAX);
export const withPinToggled = (pins: readonly string[], slug: string): string[] =>
  pins.includes(slug) ? pins.filter((s) => s !== slug) : [slug, ...pins];

// ---------- markdown ----------

/** Obsidian-isms the shared renderer does not know: comments, `![[img]]` embeds, chat visualization blocks, the H1. */
export function prepareMarkdown(md: string, titleFor?: (slug: string) => string | undefined): string {
  let s = md.replace(/<!--[\s\S]*?-->/g, "");
  // a bare [[slug]] reads as the page title (a table-cell `\|` separator is already unescaped by the parser)
  if (titleFor)
    s = s.replace(/\[\[([^\[\]|#\n]+)(#[^\[\]|\n]*)?\]\]/g, (m, slug: string) => {
      const t = titleFor(slug.trim())?.replace(/[\[\]|]/g, " ");
      return t ? `[[${slug.trim()}|${t}]]` : m;
    });
  s = s.replace(
    /```dataviewjs\n[\s\S]*?const path = "([^"]+)";[\s\S]*?```/g,
    (_m, p: string) => `[Open the visualization](/api/assets/chat?path=${encodeURIComponent(p)})`,
  );
  // `![alt](../raw/…)` (an image in raw/, written relative to wiki/ as Obsidian reads it) → the vault image route
  s = s.replace(/!\[([^\]]*)\]\(\.\.\/(raw\/[^)\s]+)\)/g, (_m, alt: string, path: string) =>
    `![${alt}](/api/assets/vault?name=${encodeURIComponent(path)})`);
  s = s.replace(/!\[\[([^\]|]+)(?:\\?\|[^\]]*)?\]\]/g, (_m, name: string) => {
    const n = name.trim();
    return `![${n}](/api/assets/vault?name=${encodeURIComponent(n)})`;
  });
  return s.replace(/^\s*#\s+[^\n]*\n/, "");
}

/** `[[slug#heading]]` links to the page `slug`. */
export const bareSlug = (raw: string): string => raw.split("#")[0]!.trim();

// ---------- search box ----------

export function scoreTitle(p: PageCard, q: string): number {
  const t = p.title.toLowerCase();
  const s = p.id.toLowerCase();
  if (t === q) return 100;
  if (t.startsWith(q)) return 80;
  if (t.includes(` ${q}`)) return 60;
  if (t.includes(q)) return 50;
  if (s.includes(q.replace(/\s+/g, "-"))) return 40;
  const terms = q.split(/\s+/);
  return terms.length > 1 && terms.every((x) => t.includes(x) || s.includes(x)) ? 30 : 0;
}

export function suggest(g: LinkGraph, query: string, limit = 8): PageCard[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return [...g.byId.values()]
    .map((p) => [scoreTitle(p, q) + Math.min(g.inn.get(p.id)?.size ?? 0, 20) / 10, p] as const)
    .filter(([sc]) => sc >= 30)
    .sort((x, y) => y[0] - x[0])
    .slice(0, limit)
    .map(([, p]) => p);
}

/** A typed title or slug -> the slug, else the text itself. */
export function resolveInput(g: LinkGraph, v: string): string {
  const t = v.trim();
  if (g.byId.has(t)) return t;
  const low = t.toLowerCase();
  for (const p of g.byId.values()) if (p.title.toLowerCase() === low) return p.id;
  return t;
}

/** Split text into plain and matching parts for highlighting (no HTML involved). */
export function highlightParts(text: string, query: string): { text: string; hit: boolean }[] {
  const terms = query.toLowerCase().split(/\s+/).filter((t) => t.length > 1);
  if (!terms.length) return [{ text, hit: false }];
  const re = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "ig");
  return text
    .split(re)
    .filter(Boolean)
    .map((part) => ({ text: part, hit: terms.includes(part.toLowerCase()) }));
}

// ---------- browse ----------

export const SORTS = ["links", "recent", "title", "year", "length"] as const;
export type Sort = (typeof SORTS)[number];

export function sortCards(g: LinkGraph, cards: readonly PageCard[], sort: Sort): PageCard[] {
  const deg = (c: PageCard) => degree(g, c.id);
  const by: Record<Sort, (a: PageCard, b: PageCard) => number> = {
    links: (a, b) => deg(b) - deg(a),
    recent: (a, b) => mtimeOf(b) - mtimeOf(a),
    title: (a, b) => a.title.localeCompare(b.title),
    year: (a, b) => (b.year ?? 0) - (a.year ?? 0),
    length: (a, b) => b.words - a.words,
  };
  return [...cards].sort(by[sort]);
}

export function filterCards(cards: readonly PageCard[], f: { layer?: string; type?: string }): PageCard[] {
  return cards.filter((c) => (!f.type || c.type === f.type) && (!f.layer || layerOf(c.type) === f.layer));
}

// ---------- home ----------

const DEPTH_RANK: Record<string, number> = { listed: 0, easy: 1, full: 2, deep: 3 };

export interface HomeSections {
  topics: PageCard[];
  questions: PageCard[];
  people: PageCard[];
  deep: PageCard[];
  recent: PageCard[];
  worthReading: PageCard[];
  orphans: PageCard[];
  counts: Map<string, number>;
}

export function homeSections(g: LinkGraph): HomeSections {
  const all = [...g.byId.values()];
  const inn = (c: PageCard) => g.inn.get(c.id)?.size ?? 0;
  const out = (c: PageCard) => g.out.get(c.id)?.size ?? 0;
  const counts = new Map<string, number>();
  for (const p of all) counts.set(p.type, (counts.get(p.type) ?? 0) + 1);
  const isSource = (c: PageCard) => layerOf(c.type) === "source";
  const rank = (c: PageCard) => DEPTH_RANK[c.depth] ?? 0;
  return {
    counts,
    topics: all.filter((p) => p.type === "topic" && out(p) > 0).sort((a, b) => degree(g, b.id) - degree(g, a.id)),
    questions: all
      .filter((p) => p.type === "question" && p.status !== "resolved")
      .sort((a, b) => degree(g, b.id) - degree(g, a.id)),
    people: all.filter((p) => p.type === "person").sort((a, b) => inn(b) - inn(a)),
    deep: all
      .filter((p) => isSource(p) && rank(p) >= 2)
      .sort((a, b) => rank(b) - rank(a) || b.words - a.words),
    recent: [...all].sort((a, b) => mtimeOf(b) - mtimeOf(a)).slice(0, 10),
    worthReading: all
      .filter((p) => isSource(p) && inn(p) >= 3 && rank(p) < 2 && p.words < 450)
      .sort((a, b) => inn(b) - inn(a))
      .slice(0, 10),
    orphans: all.filter((p) => inn(p) === 0 && p.type !== "topic"),
  };
}

// ---------- neighbourhood ring ----------

export interface RingNode {
  id: string;
  x: number;
  y: number;
  angle: number;
  radius: number;
  dir: "out" | "in" | "both";
}
export interface Ring {
  size: number;
  centre: number;
  total: number;
  nodes: RingNode[];
  /** links between two ring nodes, drawn as arcs through the centre */
  cross: [string, string][];
}

export const RING_MAX = 26;

export function ringLayout(g: LinkGraph, slug: string, max = RING_MAX, size = 320): Ring {
  const outs = g.out.get(slug) ?? new Set<string>();
  const ins = g.inn.get(slug) ?? new Set<string>();
  const all = [...neighbours(g, slug)];
  const typeIdx = (id: string) => Object.values(LAYER_TYPES).flat().indexOf((g.byId.get(id)?.type ?? "") as never);
  const ring = all
    .sort((a, b) => degree(g, b) - degree(g, a) || a.localeCompare(b))
    .slice(0, max)
    .sort((a, b) => typeIdx(a) - typeIdx(b) || a.localeCompare(b));
  const centre = size / 2;
  const R = size * 0.38;
  const nodes: RingNode[] = ring.map((id, i) => {
    const angle = (2 * Math.PI * i) / ring.length - Math.PI / 2;
    return {
      id,
      angle,
      x: centre + R * Math.cos(angle),
      y: centre + R * Math.sin(angle),
      radius: Math.min(9, 4 + Math.sqrt(degree(g, id)) * 0.9),
      dir: outs.has(id) && ins.has(id) ? "both" : outs.has(id) ? "out" : "in",
    };
  });
  const inRing = new Set(ring);
  const cross: [string, string][] = [];
  for (const s of ring) for (const t of g.out.get(s) ?? []) if (t !== slug && inRing.has(t)) cross.push([s, t]);
  return { size, centre, total: all.length, nodes, cross };
}

/** A page card as a graph node, for the shared encoding (marks, colour channels, legend). */
export function cardNode(c: PageCard): GNode {
  return {
    id: c.id,
    label: c.title || c.id,
    title: c.title || c.id,
    type: c.type,
    layer: layerOf(c.type) ?? "source",
    status: c.status,
    depth: c.depth,
    areas: c.areas,
    year: null,
    inDegree: 0,
    outDegree: 0,
    path: "",
    added: "",
    changed: "",
    preview: c.preview,
    properties: {},
  };
}
