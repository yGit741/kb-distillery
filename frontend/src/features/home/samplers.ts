import { buildNeighborMap, type NeighborMap } from "@/features/graph/graphData";
import { betweenness, computeImportance, visibleAdjacency } from "@/features/graph/lab/importance";
import { DEFAULT_LAB } from "@/features/graph/lab/config";
import type { GLink, GNode } from "@/features/graph/types";

/** Most nodes and links one card draws: a card is a taste, not a second graph. */
export const MAX_NODES = 15;
export const MAX_LINKS = 25;
/** A card with fewer nodes than this is not shown (never an empty or single-dot card). */
export const MIN_NODES = 3;

/** A hand-picked card (from a share profile): pages to show, the one to centre, one line saying why. */
export interface CardDef {
  title: string;
  pages: readonly string[];
  focus?: string;
  caption?: string;
}

export type SampleKind = "curated" | "random" | "bridge" | "question" | "thin" | "newest";

export interface Sample {
  kind: SampleKind;
  title: string;
  caption: string;
  focus: string;
  nodes: string[];
  links: [string, string][];
}

export interface Vault {
  byId: ReadonlyMap<string, GNode>;
  neighbors: NeighborMap;
  /** Pages a card may draw: no unread `listed` stubs. */
  eligible: ReadonlySet<string>;
  score: ReadonlyMap<string, number>;
  between: ReadonlyMap<string, number>;
  links: readonly Pick<GLink, "source" | "target">[];
}

const isStub = (n: GNode) => n.layer === "source" && (!n.depth || n.depth === "listed");

/** Index the snapshot once; every sampler reads this. */
export function indexVault(nodes: readonly GNode[], links: readonly Pick<GLink, "source" | "target">[]): Vault {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const eligible = new Set(nodes.filter((n) => !isStub(n)).map((n) => n.id));
  const kept = links.filter((l) => eligible.has(l.source) && eligible.has(l.target));
  const neighbors = buildNeighborMap(kept);
  const imp = computeImportance({ visible: eligible, byId, neighbors, cfg: DEFAULT_LAB });
  const between = betweenness(visibleAdjacency(eligible, neighbors));
  return { byId, neighbors, eligible, score: imp.score, between, links: kept };
}

/** mulberry32: small, seedable, good enough to pick cards. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function weightedPick(ids: readonly string[], weight: (id: string) => number, rand: () => number): string | undefined {
  if (!ids.length) return undefined;
  const w = ids.map((id) => Math.max(0, weight(id)));
  const total = w.reduce((a, b) => a + b, 0);
  if (total <= 0) return ids[Math.floor(rand() * ids.length)];
  let r = rand() * total;
  for (let i = 0; i < ids.length; i++) if ((r -= w[i] ?? 0) <= 0) return ids[i];
  return ids[ids.length - 1];
}

const pick = (ids: readonly string[], rand: () => number) => ids[Math.floor(rand() * ids.length)];
const titleOf = (v: Vault, id: string) => v.byId.get(id)?.title || id;

/**
 * Links among `ids`, capped. The focus's own links go first so the cap never cuts a node loose: a node
 * without links drifts to the edge and shrinks the rest of the card to a blob.
 */
function linksAmong(v: Vault, ids: ReadonlySet<string>, focus?: string): [string, string][] {
  const out: [string, string][] = [];
  const seen = new Set<string>();
  const touches = (l: Pick<GLink, "source" | "target">) => l.source === focus || l.target === focus;
  for (const pass of [true, false]) {
    for (const l of v.links) {
      if (out.length >= MAX_LINKS) return out;
      if (touches(l) !== pass || !ids.has(l.source) || !ids.has(l.target) || l.source === l.target) continue;
      const k = l.source < l.target ? `${l.source}|${l.target}` : `${l.target}|${l.source}`;
      if (seen.has(k)) continue;
      seen.add(k);
      out.push([l.source, l.target]);
    }
  }
  return out;
}

/** The focus plus its best-scored eligible neighbours and the links among them, both capped. */
export function neighbourhood(v: Vault, focus: string, extra: readonly string[] = []): { nodes: string[]; links: [string, string][] } {
  const keep = new Set<string>([focus, ...extra.filter((id) => v.eligible.has(id))]);
  const around = [...new Set(v.neighbors.get(focus) ?? [])].filter((id) => v.eligible.has(id) && !keep.has(id));
  around.sort((a, b) => (v.score.get(b) ?? 0) - (v.score.get(a) ?? 0) || a.localeCompare(b));
  for (const id of around) {
    if (keep.size >= MAX_NODES) break;
    keep.add(id);
  }
  const nodes = [...keep].slice(0, MAX_NODES);
  return { nodes, links: linksAmong(v, new Set(nodes), focus) };
}

function make(v: Vault, kind: SampleKind, focus: string | undefined, caption: string): Sample | null {
  if (!focus || !v.eligible.has(focus)) return null;
  const { nodes, links } = neighbourhood(v, focus);
  if (nodes.length < MIN_NODES) return null;
  return { kind, title: titleOf(v, focus), caption, focus, nodes, links };
}

/** A hand-picked card: its own pages (those present in this build), else the focus's neighbourhood. */
export function curated(v: Vault, def: CardDef): Sample | null {
  const pages = def.pages.filter((id) => v.eligible.has(id));
  const focus = def.focus && v.eligible.has(def.focus) ? def.focus : pages[0];
  if (!focus) return null;
  const nodes = pages.length >= MIN_NODES ? [...new Set([focus, ...pages])].slice(0, MAX_NODES) : neighbourhood(v, focus, pages).nodes;
  if (nodes.length < MIN_NODES) return null;
  return { kind: "curated", title: def.title, caption: def.caption ?? "", focus, nodes, links: linksAmong(v, new Set(nodes), focus) };
}

type Sampler = (v: Vault, rand: () => number) => Sample | null;

/** Pages with enough eligible neighbours to make a card. */
const connected = (v: Vault) => [...v.eligible].filter((id) => (v.neighbors.get(id)?.length ?? 0) >= MIN_NODES - 1).sort();

export const SAMPLERS: Record<Exclude<SampleKind, "curated">, Sampler> = {
  random: (v, rand) =>
    make(v, "random", weightedPick(connected(v), (i) => v.score.get(i) ?? 0, rand), "A page and what it links to, picked at random, weighted to well-read pages."),
  bridge: (v, rand) => {
    const spans = (id: string) => new Set((v.neighbors.get(id) ?? []).flatMap((j) => v.byId.get(j)?.areas ?? [])).size;
    const top = connected(v)
      .filter((id) => spans(id) >= 2)
      .sort((a, b) => (v.between.get(b) ?? 0) - (v.between.get(a) ?? 0))
      .slice(0, 12);
    return make(v, "bridge", pick(top, rand), "A bridge: many shortest paths between topics run through it.");
  },
  question: (v, rand) => {
    const pool = connected(v).filter((id) => {
      const n = v.byId.get(id);
      return n?.type === "question" && /open|partial/.test(n.status);
    });
    return make(v, "question", pick(pool, rand), "An open question and the pages that bear on it.");
  },
  newest: (v, rand) => {
    const papers = connected(v).filter((id) => v.byId.get(id)?.layer === "source" && v.byId.get(id)?.year);
    const latest = Math.max(0, ...papers.map((id) => v.byId.get(id)?.year ?? 0));
    return make(v, "newest", pick(papers.filter((id) => (v.byId.get(id)?.year ?? 0) >= latest - 1), rand), "One of the most recent papers in the vault.");
  },
  thin: (v, rand) => {
    const sources = (id: string) => (v.neighbors.get(id) ?? []).filter((j) => v.byId.get(j)?.layer === "source").length;
    const pool = connected(v).filter((id) => ["idea", "topic"].includes(v.byId.get(id)?.type ?? "") && sources(id) <= 1);
    return make(v, "thin", pick(pool, rand), "Well connected, but backed by at most one source.");
  },
};

export const RANDOM_ORDER: readonly Exclude<SampleKind, "curated">[] = ["random", "bridge", "question", "newest", "thin"];

/** One card per sampler kind, in order; kinds with nothing to show are dropped. `seeds[kind]` rerolls one card. */
export function sampleAll(v: Vault, seeds: Readonly<Partial<Record<SampleKind, number>>>): Sample[] {
  const out: Sample[] = [];
  for (const kind of RANDOM_ORDER) {
    const s = SAMPLERS[kind](v, rng(seeds[kind] ?? 1));
    if (s) out.push(s);
  }
  return out;
}

/** `/graph` search params that open a sample in the full graph, centred on `focus`. */
export function graphSearch(s: Pick<Sample, "nodes" | "focus">, focus = s.focus): Record<string, string> {
  return { pages: s.nodes.join(","), select: focus, focus };
}

/** Knowledge-node cards: one page shown as text (facts, opening, neighbours), not as a graph. */
export type NodeKind = "idea" | "source" | "question";

export const NODE_ORDER: readonly NodeKind[] = ["idea", "source", "question"];

export const NODE_CAPTION: Record<NodeKind, string> = {
  idea: "An idea or topic note",
  source: "A digested source",
  question: "A research question",
};

const NODE_FILTER: Record<NodeKind, (n: GNode) => boolean> = {
  idea: (n) => n.type === "idea" || n.type === "topic",
  source: (n) => n.layer === "source" && ["easy", "full", "deep"].includes(n.depth),
  question: (n) => n.type === "question",
};

/** Most neighbours a node card lists. */
export const NODE_NEIGHBOURS = 6;

export interface NodeSample {
  kind: NodeKind;
  id: string;
  /** Best-scored neighbours, for the chips under the excerpt. */
  neighbours: string[];
}

/** One page of the given kind, weighted to well-read, well-linked pages. */
export function sampleNode(v: Vault, kind: NodeKind, rand: () => number): NodeSample | null {
  const pool = connected(v).filter((id) => {
    const n = v.byId.get(id);
    return !!n && NODE_FILTER[kind](n);
  });
  const id = weightedPick(pool, (i) => v.score.get(i) ?? 0, rand);
  if (!id) return null;
  const neighbours = [...new Set(v.neighbors.get(id) ?? [])]
    .filter((j) => v.eligible.has(j))
    .sort((a, b) => (v.score.get(b) ?? 0) - (v.score.get(a) ?? 0) || a.localeCompare(b))
    .slice(0, NODE_NEIGHBOURS);
  return { kind, id, neighbours };
}

export function sampleNodes(v: Vault, seeds: Readonly<Partial<Record<NodeKind, number>>>): NodeSample[] {
  return NODE_ORDER.map((k) => sampleNode(v, k, rng(seeds[k] ?? 1))).filter((s): s is NodeSample => !!s);
}

/** About how much of a page a node card shows before "Read". */
export const EXCERPT_CHARS = 600;

/**
 * The opening prose of a page for a card: no front matter, headings, tables or `> Part of` lines, nothing
 * from `## My notes` on, and no paragraph that only repeats the title (question pages restate it). Whole
 * paragraphs up to about EXCERPT_CHARS (at least one, so a long first paragraph still shows).
 */
export function excerpt(markdown: string, max = EXCERPT_CHARS, title = ""): string {
  let body = markdown.replace(/^---\n[\s\S]*?\n---\n/, "");
  const notes = body.search(/^##\s+My notes\b/m);
  if (notes >= 0) body = body.slice(0, notes);
  const plain = (s: string) => s.replace(/\*\*[^*]+:\*\*/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim().toLowerCase();
  const t = plain(title);
  const paras = body
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter((p) => p && !/^#{1,6}\s/.test(p) && !/^\|/.test(p) && !/^>\s*(Part|Lecture) of/.test(p) && !(t && plain(p) === t));
  const out: string[] = [];
  let len = 0;
  for (const p of paras) {
    if (out.length && len + p.length > max) break;
    out.push(p);
    len += p.length;
  }
  return out.join("\n\n");
}
