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

/**
 * How well a concept is backed by sources (the graph's Health view). A problem takes a status hue, a healthy page
 * stays grey. One set per ground, like the area hues: the light set is tuned for warm paper, and its ochre and red
 * turn brown and heavy on graphite, so the dark set lifts the same three meanings (each 5:1 or more on graphite).
 */
export const SUPPORT_COLORS = {
  none: "#dc2626",
  one: "#c2820c",
  many: "#7c808b",
} as const;
export const SUPPORT_COLORS_DARK = {
  none: "#ff6b7a",
  one: "#eeb04a",
  many: "#8f95a5",
} as const;

/** People on the dark ground (the graph's deep person ink vanishes on graphite): a slate that still carries white
 *  initials (5:1) and stands 3:1 off the ground. */
export const PERSON_INK_DARK = "#606B87";

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
export const supportColor = (support: keyof typeof SUPPORT_COLORS, dark = false): string =>
  (dark ? SUPPORT_COLORS_DARK : SUPPORT_COLORS)[support];
export const pileColor = (pile?: string | null): string => lookup(PILE_COLORS, pile);

/** Stable colour per area slug (same string hash as graph.js, so colours match the legacy graph). */
export function areaColor(area?: string | null): string {
  const key = area || "none";
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return AREA_COLORS[h % AREA_COLORS.length] as string;
}

/**
 * The graph's topic colours (flag ui.embedding-views): the graph's categorical palette (ColorBrewer Paired) without
 * its red, pink, orange and amber slots, which are kept for problems; strong hues first. Topic 0 is the largest; ids
 * past the list wrap.
 */
export const TOPIC_COLORS: readonly string[] = ["#1F78B4", "#33A02C", "#6A3D9A", "#17BECF", "#00797F", "#A6CEE3", "#B2DF8A", "#CAB2D6"];
/** The reds, oranges and ambers a topic must never take (problem colours, in either palette). */
export const PROBLEM_HUES: readonly string[] = ["#ff6b7a", "#ff9e64", "#f6c177", "#e0af68", "#e31a1c", "#fb9a99", "#ff7f00", "#fdbf6f", "#d9b43b", "#b15928"];
export const topicColor = (id: number): string => TOPIC_COLORS[((id % TOPIC_COLORS.length) + TOPIC_COLORS.length) % TOPIC_COLORS.length]!;

/** A semantic cluster's colour (Embedding map): cluster 0 is the largest; ids past the palette wrap. */
export const clusterColor = (id: number): string => AREA_COLORS[((id % AREA_COLORS.length) + AREA_COLORS.length) % AREA_COLORS.length] as string;

/**
 * Area colours to choose from (variant `area-colours`), from the canvas-palette mockup: eight hues each, a light and
 * a dark set that belong together. Field is calm and soft; Clear is crisp. Areas past the eighth are "Other areas".
 * "current" keeps the graph's ColorBrewer Paired twelve (features/graph/style.ts AREA_PALETTE).
 */
export const AREA_PALETTES: Readonly<Record<"field" | "clear", { light: readonly string[]; dark: readonly string[] }>> = {
  field: {
    light: ["#4a7fc1", "#d4704a", "#3fa384", "#d1a23a", "#c46a96", "#5f9a3c", "#7a68c9", "#c9585a"],
    dark: ["#5b84e0", "#d4644f", "#2f9f7c", "#b38526", "#c25d8d", "#4d9a3b", "#8676dd", "#cc5a5a"],
  },
  clear: {
    light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
    dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"],
  },
};
