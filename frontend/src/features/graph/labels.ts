import type { NeighborMap } from "./graphData";
import { degreeOf, type GNode } from "./types";

export type LabelMode = "auto" | "all" | "hover" | "off";
export type LabelField = "title" | "slug";

export const LABEL_MODES: readonly { id: LabelMode; label: string }[] = [
  { id: "auto", label: "Hubs, then more as you zoom" },
  { id: "all", label: "Every visible page" },
  { id: "hover", label: "Hovered page and selection" },
  { id: "off", label: "Only the hovered page" },
];

/** About a dozen collection and topic labels at fit zoom. */
export const HUB_BUDGET = 12;

export interface LabelInput {
  visible: ReadonlySet<string>;
  byId: ReadonlyMap<string, GNode>;
  neighbors: NeighborMap;
  hovered: string | null;
  selected: ReadonlySet<string>;
  mode: LabelMode;
  /** Types whose every label is shown (the legend's "Aa"). */
  typeLabels: ReadonlySet<string>;
  /** Current zoom divided by the zoom of the last fit; 1 = fit zoom. */
  zoomRatio: number;
}

export const RANK = { hover: 0, selected: 1, near: 2, type: 3, hub: 4, all: 5 } as const;

const isHub = (n: GNode) => n.layer === "collection" || n.type === "topic";

/** How many hub labels at this zoom: the budget at fit zoom, growing faster than the zoom as you get closer. */
export const hubCount = (zoomRatio: number, budget = HUB_BUDGET): number =>
  Math.round(budget * Math.max(1, zoomRatio) ** 1.5);

/**
 * Which pages are labelled, ranked (lower = more important, drawn first and never dropped by overlap).
 * The hovered page always has its label, a selection labels itself and its neighbours; on top of that the
 * mode picks hub labels (collections and topics by link count; any page by link count once zoomed in).
 */
export function labelRanks(i: LabelInput): Map<string, number> {
  const out = new Map<string, number>();
  const put = (id: string, rank: number) => {
    if (!i.visible.has(id)) return;
    const prev = out.get(id);
    if (prev === undefined || rank < prev) out.set(id, rank);
  };
  if (i.hovered) {
    put(i.hovered, RANK.hover);
    if (i.mode !== "off") (i.neighbors.get(i.hovered) ?? []).forEach((n) => put(n, RANK.near));
  }
  for (const id of i.selected) {
    put(id, RANK.selected);
    (i.neighbors.get(id) ?? []).forEach((n) => put(n, RANK.near));
  }
  if (i.typeLabels.size) for (const id of i.visible) if (i.typeLabels.has(i.byId.get(id)?.type ?? "")) put(id, RANK.type);
  if (i.mode === "all") {
    i.visible.forEach((id) => put(id, RANK.all));
  } else if (i.mode === "auto") {
    const nodes = [...i.visible].map((id) => i.byId.get(id)).filter((n): n is GNode => !!n);
    let pool = nodes.filter(isHub);
    if (!pool.length || i.zoomRatio >= 2) pool = nodes;
    pool.sort((a, b) => degreeOf(b) - degreeOf(a) || a.id.localeCompare(b.id));
    pool.slice(0, hubCount(i.zoomRatio)).forEach((n) => put(n.id, RANK.hub));
  }
  return out;
}

export function shortSlug(slug: string): string {
  const parts = slug.split("-");
  return parts.length <= 4 ? slug : `${parts.slice(0, 3).join("-")}…`;
}

export function labelText(n: GNode, field: LabelField, full = false): string {
  const text = field === "slug" ? n.id : n.title || n.id;
  return full || text.length <= 42 ? text : `${text.slice(0, 40)}…`;
}

export interface Box {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface Placed {
  id: string;
  rank: number;
  deg: number;
  box: Box;
}

const overlaps = (a: Box, b: Box) => a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;

/**
 * Draw order and overlap test: most important first; a label that would overlap one already placed is
 * skipped, except the hovered one (rank 0), which is always drawn. Coarse grid buckets keep it cheap.
 */
export function declutter(candidates: readonly Placed[], cell: number): Placed[] {
  const sorted = [...candidates].sort((a, b) => a.rank - b.rank || b.deg - a.deg || a.id.localeCompare(b.id));
  const grid = new Map<string, Box[]>();
  const keys = (b: Box) => {
    const out: string[] = [];
    for (let gx = Math.floor(b.x1 / cell); gx <= Math.floor(b.x2 / cell); gx++)
      for (let gy = Math.floor(b.y1 / cell); gy <= Math.floor(b.y2 / cell); gy++) out.push(`${gx},${gy}`);
    return out;
  };
  const kept: Placed[] = [];
  for (const c of sorted) {
    const ks = keys(c.box);
    if (c.rank > RANK.hover && ks.some((k) => (grid.get(k) ?? []).some((q) => overlaps(c.box, q)))) continue;
    ks.forEach((k) => {
      const list = grid.get(k);
      if (list) list.push(c.box);
      else grid.set(k, [c.box]);
    });
    kept.push(c);
  }
  return kept;
}
