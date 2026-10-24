import type { GraphSnapshot } from "@/api";
import { pileColor } from "@/theme/palette";
import { withAlpha } from "./canvasTheme";
import type { GLink, GNode, RawLayer, RawLink, RawNode } from "./types";

/** Most page links drawn per pile (the strongest first): a pile feeds hundreds of pages. */
export const PILE_PAGE_LINK_CAP = 150;
export const PILE_PREFIX = "pile:";
/** Companions ride with their parent file: they are counted apart and never a scope member. */
export const COMPANION_HEADS = ["asset", "ink", "dupe", "sidecar"] as const;

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const str = (v: unknown): string => (typeof v === "string" ? v : "");

export const isPileId = (id: string): boolean => id.startsWith(PILE_PREFIX);
export const isPile = (n: { id: string }): boolean => isPileId(n.id);
export const formatOfPile = (id: string): string => id.slice(PILE_PREFIX.length);

/** The facts a pile carries, kept on the node (`n["pile"]`) like a book's partition. */
export interface PileInfo {
  format: string;
  count: number;
  source: number;
  partial: number;
  queued: number;
  skip: number;
  companions: number;
  /** Digested share of the files that are not skipped and not companions, 0..1. */
  share: number;
}

export function pileOf(n: { id: string; [k: string]: unknown }): PileInfo | null {
  const p = n["pile"];
  if (!isPileId(n.id) || !isObj(p)) return null;
  return {
    format: str(p["format"]),
    count: num(p["count"]),
    source: num(p["source"]),
    partial: num(p["partial"]),
    queued: num(p["queued"]),
    skip: num(p["skip"]),
    companions: num(p["companions"]),
    share: num(p["share"]),
  };
}

/** `head` of a disposition: "asset:raw/x.md" -> "asset", "source" -> "source". */
export const dispositionHead = (d: string | null | undefined): string => (d ?? "").split(":")[0] ?? "";
export const isCompanionDisposition = (d: string | null | undefined): boolean =>
  (COMPANION_HEADS as readonly string[]).includes(dispositionHead(d));

function pileNode(p: Record<string, unknown>): GNode {
  const format = str(p["format"]);
  const count = num(p["count"]);
  const source = num(p["source"]);
  const partial = num(p["partial"]);
  const skip = num(p["skip"]);
  const companions = num(p["companions"]);
  const nonSkip = count - skip - companions;
  return {
    id: `${PILE_PREFIX}${format}`,
    label: format,
    title: format,
    type: "pile",
    layer: "raw",
    status: "",
    depth: "",
    areas: [],
    year: null,
    inDegree: 0,
    outDegree: 0,
    path: "",
    preview: "",
    properties: {},
    pile: { format, count, source, partial, queued: num(p["queued"]), skip, companions, share: nonSkip > 0 ? (source + partial) / nonSkip : 0 },
  } as GNode;
}

/**
 * The data layer of a `?layer=raw` snapshot: one node per non-empty format (the inbox is a queue, not a
 * pile), a thin edge to each page it feeds (the strongest {@link PILE_PAGE_LINK_CAP}) and an edge between
 * two piles that share a page, a collection or a companion. Null for a plain snapshot.
 */
export function parseRawLayer(snap: GraphSnapshot): RawLayer | null {
  const rawPiles = snap["piles"];
  if (!Array.isArray(rawPiles)) return null;
  const pageIds = new Set(snap.nodes.map((n) => n.id));
  const piles: GNode[] = [];
  const links: GLink[] = [];
  const have = new Set<string>();
  for (const p of rawPiles) {
    if (!isObj(p) || str(p["format"]) === "inbox" || num(p["count"]) <= 0) continue;
    const node = pileNode(p);
    piles.push(node);
    have.add(str(p["format"]));
    const to = p["links_to_pages"];
    if (isObj(to)) {
      Object.entries(to)
        .filter(([slug]) => pageIds.has(slug))
        .slice(0, PILE_PAGE_LINK_CAP)
        .forEach(([slug, n]) => links.push({ source: node.id, target: slug, kind: "pile-page", count: num(n) }));
    }
  }
  const pl = snap["pile_links"];
  if (Array.isArray(pl)) {
    for (const l of pl) {
      if (!isObj(l)) continue;
      const a = str(l["source"]);
      const b = str(l["target"]);
      if (have.has(a) && have.has(b) && l["kind"] !== "page") {
        links.push({ source: `${PILE_PREFIX}${a}`, target: `${PILE_PREFIX}${b}`, kind: "pile-pile", count: num(l["count"]) });
      }
    }
  }
  const nodes: RawNode[] = (Array.isArray(snap["raw_nodes"]) ? (snap["raw_nodes"] as unknown[]) : []).filter(isObj).map((r) => ({
    id: str(r["id"]),
    path: str(r["path"]),
    format: str(r["format"]),
    ext: str(r["ext"]),
    disposition: str(r["disposition"]),
    companion_of: typeof r["companion_of"] === "string" ? r["companion_of"] : null,
    collection: Array.isArray(r["collection"]) ? (r["collection"] as unknown[]).map(String) : [],
    slug: typeof r["slug"] === "string" && r["slug"] ? r["slug"] : null,
    year: typeof r["year"] === "number" ? r["year"] : null,
    title: str(r["title"]),
  }));
  const rawLinks: RawLink[] = (Array.isArray(snap["raw_links"]) ? (snap["raw_links"] as unknown[]) : []).filter(isObj).map((l) => ({
    source: str(l["source"]),
    target: str(l["target"]),
    kind: str(l["kind"]),
  }));
  return { piles, links, nodes, rawLinks };
}

/** The raw files that feed one page (`raw_links` of kind `source`), companions left out. */
export function rawSourcesOf(raw: RawLayer | undefined, slug: string): RawNode[] {
  if (!raw) return [];
  const byId = new Map(raw.nodes.map((n) => [n.id, n] as const));
  const out: RawNode[] = [];
  for (const l of raw.rawLinks) {
    const n = l.target === slug && l.kind === "source" ? byId.get(l.source) : undefined;
    if (n && !isCompanionDisposition(n.disposition)) out.push(n);
  }
  return out;
}

export const pileRadius = (n: { [k: string]: unknown; id: string }): number => 7 + Math.sqrt(pileOf(n)?.count ?? 1) * 0.9;

/** A stack of discs ringed by the digested share, labelled `format · count`. */
export function drawPile(
  n: GNode & { x?: number; y?: number },
  ctx: CanvasRenderingContext2D,
  scale: number,
  c: { background: string; text: string; font: string; ring: string },
  hovered: boolean,
): void {
  const info = pileOf(n);
  if (!info || n.x == null || n.y == null) return;
  const color = pileColor(info.format);
  const r = pileRadius(n) * (hovered ? 1.12 : 1);
  for (let i = 2; i >= 0; i--) {
    ctx.beginPath();
    ctx.arc(n.x + i * r * 0.1, n.y - i * r * 0.1, r, 0, 2 * Math.PI);
    ctx.globalAlpha = 0.35 + (2 - i) * 0.3;
    ctx.fillStyle = color;
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  ctx.lineWidth = 3 / scale;
  ctx.beginPath();
  ctx.arc(n.x, n.y, r + 3 / scale, 0, 2 * Math.PI);
  ctx.strokeStyle = withAlpha(c.text, 0.25);
  ctx.stroke();
  if (info.share > 0) {
    ctx.beginPath();
    ctx.arc(n.x, n.y, r + 3 / scale, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * info.share);
    ctx.strokeStyle = c.ring;
    ctx.stroke();
  }
  const size = Math.max(11 / scale, 3);
  ctx.font = `600 ${size}px ${c.font}`;
  const text = `${info.format} · ${info.count}`;
  const w = ctx.measureText(text).width;
  ctx.fillStyle = withAlpha(c.background, 0.85);
  ctx.fillRect(n.x - w / 2 - 2 / scale, n.y + r + 6 / scale, w + 4 / scale, size + 3 / scale);
  ctx.fillStyle = c.text;
  ctx.fillText(text, n.x - w / 2, n.y + r + 6 / scale + size);
}
