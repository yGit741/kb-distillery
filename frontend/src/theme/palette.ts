/**
 * The ONE data palette, keyed by the data model: page `type`, `kind`, `depth`, concept `status`,
 * `area`, raw `pile`. Values are copied unchanged from the legacy maps (TYPE_COLORS in graph.js:97
 * and explore.js:4, STATUS/AREA/PILE_COLORS in graph.js) and assigned to the new kinds; where one
 * old colour served several kinds, each kind keeps it. Where the two legacy TYPE_COLORS maps
 * disagreed (`scope`), graph.js wins. No old page-type names appear here.
 */
import type { Depth, Kind, PageType } from "@/api/model";

export const UNKNOWN_COLOR = "#6c7086";

/** kind -> colour (the graph/pages node colour). */
export const KIND_COLORS: Record<Kind | "scope" | "draft", string> = {
  // sources
  paper: "#ff6b7a",
  part: "#eab0ee",
  lecture: "#ffc777",
  article: "#4fd6be",
  video: "#f7768e",
  conversation: "#73daca",
  "ai-chat": "#ff9e64",
  "blog-post": "#ff79c6",
  // collections
  book: "#d16bd8",
  notebook: "#c099ff",
  course: "#2ac3de",
  series: "#7dcfff",
  // concepts
  topic: "#9ece6a",
  idea: "#7aa2ff",
  question: "#f6c177",
  person: "#bb9af7",
  // graph-only
  scope: "#e6c07b",
  draft: "#e0af68",
};

/** type -> colour, for the three-way legend: one representative kind colour each. */
export const TYPE_COLORS: Record<PageType, string> = {
  source: KIND_COLORS.paper,
  collection: KIND_COLORS.book,
  concept: KIND_COLORS.idea,
};

/** Reading depth of a source (catalog -> deep), from the old to-read / reading / digested / resolved colours. */
export const DEPTH_COLORS: Record<Depth, string> = {
  catalog: "#6c7086",
  easy: "#7aa2ff",
  full: "#9ece6a",
  deep: "#73daca",
};

/** Maturity of a concept page (seed/growing/solid; questions: open/partial/resolved). */
export const STATUS_COLORS = {
  seed: "#565f89",
  growing: "#7aa2ff",
  solid: "#9ece6a",
  open: "#f6c177",
  partial: "#e0af68",
  resolved: "#73daca",
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
} as const;

const lookup = (map: Readonly<Record<string, string>>, key: string | null | undefined): string =>
  (key != null && Object.prototype.hasOwnProperty.call(map, key) ? map[key] : undefined) ?? UNKNOWN_COLOR;

export const kindColor = (kind?: string | null): string => lookup(KIND_COLORS, kind);
export const typeColor = (type?: string | null): string => lookup(TYPE_COLORS, type);
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
