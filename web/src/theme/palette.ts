/**
 * The ONE data palette, keyed by the data model: page `type` (grouped by `layer`), source `depth`,
 * `status`, `area`, raw `pile`. Values are copied unchanged from the legacy maps (TYPE_COLORS in
 * graph.js:97 and explore.js:4, STATUS/AREA/PILE_COLORS in graph.js); where the two TYPE_COLORS
 * maps disagreed (`scope`), graph.js wins.
 */
import type { Depth, Layer, PageType } from "@/api/model";

export const UNKNOWN_COLOR = "#6c7086";

/** type -> colour (the graph/pages node colour). */
export const TYPE_COLORS: Record<PageType, string> = {
  // source
  paper: "#ff6b7a",
  part: "#eab0ee",
  lecture: "#ffc777",
  article: "#4fd6be",
  video: "#f7768e",
  mail: "#73daca",
  "ai-chat": "#ff9e64",
  "blog-post": "#ff79c6",
  // collection
  book: "#d16bd8",
  notebook: "#c099ff",
  course: "#2ac3de",
  series: "#7dcfff",
  scope: "#e6c07b",
  // concept
  topic: "#9ece6a",
  idea: "#7aa2ff",
  question: "#f6c177",
  person: "#bb9af7",
  "distilled-think": "#e0af68",
};

/** layer -> colour, for a three-way legend: one representative type colour each. */
export const LAYER_COLORS: Record<Layer, string> = {
  source: TYPE_COLORS.paper,
  collection: TYPE_COLORS.book,
  concept: TYPE_COLORS.idea,
};

/** Depth of a source, listed -> deep (the old to-read / reading / digested / resolved colours). */
export const DEPTH_COLORS: Record<Depth, string> = {
  listed: "#6c7086",
  easy: "#7aa2ff",
  full: "#9ece6a",
  deep: "#73daca",
};

/** Page status: reading state of sources and collections, maturity of ideas/topics, state of questions and drafts. */
export const STATUS_COLORS = {
  "to-read": "#6c7086",
  reading: "#7aa2ff",
  digested: "#9ece6a",
  seed: "#565f89",
  growing: "#7aa2ff",
  solid: "#9ece6a",
  open: "#f6c177",
  partial: "#e0af68",
  resolved: "#73daca",
  review: "#e0af68",
  applied: "#73daca",
  archived: "#565f89",
} as const;

export const AREA_COLORS = [
  "#7aa2ff", "#ff6b7a", "#9ece6a", "#f6c177", "#bb9af7",
  "#73daca", "#e0af68", "#ff9e64", "#89ddff", "#c792ea",
] as const;

export const PILE_COLORS = {
  "printed-docs": "#ff6b7a",
  handwritten: "#c099ff",
  presentations: "#ffc777",
  "llm-chats": "#ff9e64",
  emails: "#73daca",
  "web-clips": "#4fd6be",
  images: "#7dcfff",
  videos: "#e0af68",
} as const;

const lookup = (map: Readonly<Record<string, string>>, key: string | null | undefined): string =>
  (key != null && Object.prototype.hasOwnProperty.call(map, key) ? map[key] : undefined) ?? UNKNOWN_COLOR;

export const typeColor = (type?: string | null): string => lookup(TYPE_COLORS, type);
export const layerColor = (layer?: string | null): string => lookup(LAYER_COLORS, layer);
export const depthColor = (depth?: string | null): string => lookup(DEPTH_COLORS, depth);
export const statusColor = (status?: string | null): string => lookup(STATUS_COLORS, status);
export const pileColor = (pile?: string | null): string => lookup(PILE_COLORS, pile);

/** Stable colour per area slug (same string hash as graph.js, so colours match the legacy graph). */
export function areaColor(area?: string | null): string {
  const key = area || "none";
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return AREA_COLORS[h % AREA_COLORS.length] as string;
}

/** A semantic cluster's colour (Embedding map): cluster 0 is the largest; ids past the palette wrap. */
export const clusterColor = (id: number): string => AREA_COLORS[((id % AREA_COLORS.length) + AREA_COLORS.length) % AREA_COLORS.length] as string;
