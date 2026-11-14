import { readCanvasColors } from "./encoding/theme";
import { depthColor, layerColor, statusColor, supportColor, topicColor, typeColor, UNKNOWN_COLOR } from "@/theme/palette";
import { areaDisplay } from "./displayNames";
import { markOf, RING_BOOST } from "./encoding/spec";
import { degreeOf, type GNode } from "./types";

export type ColorBy = "type" | "layer" | "depth" | "status" | "area" | "degree" | "evidence" | "score" | "none" | "format" | "recency" | "added" | "support" | "topic";
export type SizeBy = "connections" | "in" | "out" | "uniform" | "tier" | "evidence" | "score" | "gap" | "logdeg";

/** Size and colour modes that read a 0..1 signal of the importance score (lab/importance) instead of the page. */
export const METRIC_SIZES: ReadonlySet<SizeBy> = new Set(["evidence", "score", "gap"]);
export const METRIC_COLORS: ReadonlySet<ColorBy> = new Set(["evidence", "score"]);

export const COLOR_BY: readonly { id: ColorBy; label: string }[] = [
  { id: "type", label: "Type" },
  { id: "layer", label: "Layer" },
  { id: "depth", label: "Depth (sources)" },
  { id: "status", label: "Status" },
  { id: "area", label: "Primary area" },
  { id: "degree", label: "Link count" },
  { id: "score", label: "Importance score" },
  { id: "none", label: "One colour" },
];

export const SIZE_BY: readonly { id: SizeBy; label: string }[] = [
  { id: "tier", label: "Type tier" },
  { id: "evidence", label: "Evidence (digested sources)" },
  { id: "score", label: "Importance score" },
  { id: "gap", label: "Thin spot" },
  { id: "logdeg", label: "Link count (log)" },
  { id: "connections", label: "Connections (in + out, sqrt)" },
  { id: "in", label: "In-links" },
  { id: "out", label: "Out-links" },
  { id: "uniform", label: "Uniform" },
];

const DEGREE_BANDS = [
  { min: 12, label: "12+ links", color: "#ff6b7a" },
  { min: 6, label: "6–11 links", color: "#f6c177" },
  { min: 2, label: "2–5 links", color: "#7aa2ff" },
  { min: 0, label: "0–1 links", color: "#565f89" },
] as const;

const degreeBand = (n: GNode) => DEGREE_BANDS.find((b) => degreeOf(n) >= b.min) ?? DEGREE_BANDS[3];

/** Light to dark blue for a 0..1 signal. */
export function sequentialColor(t: number): string {
  const c = Math.max(0, Math.min(1, t));
  const mix = (a: number, b: number) => Math.round(a + (b - a) * c);
  return `rgb(${mix(201, 31)}, ${mix(211, 91)}, ${mix(224, 214)})`;
}

/**
 * Area colours: ColorBrewer Paired 12, dark hues first, so the six largest areas get the six strong colours and
 * the next six their light partners; every area past the twelfth is "Other areas" (grey), a page without one
 * "No area" (lighter grey). Twelve is past the ~8 the eye tells apart on 5px dots; the pairs' lightness step and
 * the hover spotlight carry the rest.
 */
export const AREA_PALETTE: readonly string[] = [
  "#1F78B4", "#33A02C", "#E31A1C", "#FF7F00", "#6A3D9A", "#B15928",
  // Paired's pale yellow (#FFFF99) vanishes on the light canvas: a mustard in its slot
  "#A6CEE3", "#B2DF8A", "#FB9A99", "#FDBF6F", "#CAB2D6", "#D9B43B",
];
/** The two greys sit far apart in lightness: "Other areas" a solid mid grey, "No area" a faint one. */
export const OTHER_GREY = "#7C808B";
/** No area: darker than the edges' grey, so a page without one never reads as a link. */
export const NONE_GREY = "#B3B7C3";
/** People have no area of their own: a deep ink, unlike any area colour and unlike the edges. */
export const PERSON_INK = "#2F3542";
export const PEOPLE = "People";
export const OTHER_AREAS = "Other areas";
export const NO_AREA = "No area";
let AREA_SLOT: ReadonlyMap<string, string> = new Map<string, string>();
/** Slot maps built over a kb where no page has an area (an imported OKF bundle): their keys are page types. */
const TYPE_KEYED = new WeakSet<ReadonlyMap<string, string>>();

/** The key a page is coloured by under the area colouring: its first area, else its type when the slots are type-keyed. */
export const areaOf = (n: Pick<GNode, "areas" | "type">, typeAsArea = false): string | undefined =>
  n.areas[0] || (typeAsArea ? n.type || undefined : undefined);

/**
 * The areas' colours by size (pages whose first area it is), largest first; ties by name. Pure: no global set.
 * Over pages none of which has an area, the page types take the slots instead, so such a kb is not all grey.
 */
export function areaSlots(nodes: readonly Pick<GNode, "areas" | "type">[]): ReadonlyMap<string, string> {
  const typeAsArea = nodes.length > 0 && !nodes.some((n) => n.areas.length > 0);
  const count = new Map<string, number>();
  for (const n of nodes) {
    const a = areaOf(n, typeAsArea);
    if (a) count.set(a, (count.get(a) ?? 0) + 1);
  }
  const ranked = [...count].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, AREA_PALETTE.length);
  const slots = new Map(ranked.map(([a], i) => [a, AREA_PALETTE[i]!]));
  if (typeAsArea) TYPE_KEYED.add(slots);
  return slots;
}

/** Whether these slots key pages by type (a kb without areas). */
export const typeKeyed = (slots: ReadonlyMap<string, string>): boolean => TYPE_KEYED.has(slots);

/** The Full Graph's area colours (`areaSlots` over its model), the default for every colouring by area. */
export function assignAreaColors(nodes: readonly GNode[]): ReadonlyMap<string, string> {
  AREA_SLOT = areaSlots(nodes);
  return AREA_SLOT;
}

/** Area slots a surface passes explicitly (Home: over the whole vault); undefined = the Full Graph's. */
export type AreaSlots = ReadonlyMap<string, string>;

/** An area's colour: its slot, grey past the palette, lighter grey for none. */
export const areaHue = (area?: string | null, slots: AreaSlots = AREA_SLOT): string => (!area ? NONE_GREY : (slots.get(area) ?? OTHER_GREY));

/**
 * How many source pages back a concept, as the Health view says it. People are not counted (a person page is not a
 * claim): they keep their own ink and their own row of the key.
 */
export type Support = "none" | "one" | "many";
export const SUPPORT_LABEL: Readonly<Record<Support, string>> = { none: "No source", one: "One source", many: "Two or more sources" };
let SUPPORT: ReadonlyMap<string, number> = new Map();
/** The source count behind each concept (./subject sourceCounts), set by the graph screen for the "support" colouring. */
export function assignSupport(counts: ReadonlyMap<string, number>): ReadonlyMap<string, number> {
  SUPPORT = counts;
  return SUPPORT;
}
export function supportOf(n: GNode, counts: ReadonlyMap<string, number> = SUPPORT): Support | null {
  if (n.layer !== "concept" || n.type === "person") return null;
  const c = counts.get(n.id) ?? 0;
  return c === 0 ? "none" : c === 1 ? "one" : "many";
}
/** A colour key with a fixed order (worst first) instead of largest first. */
export const KEY_ORDER: Readonly<Partial<Record<ColorBy, readonly string[]>>> = { support: [SUPPORT_LABEL.none, SUPPORT_LABEL.one, SUPPORT_LABEL.many] };
/** Topics (flag ui.embedding-views): each page's embedding cluster and each cluster's name, set once the embedding loads. */
let TOPICS: { of: ReadonlyMap<string, number>; names: ReadonlyMap<number, string> } = { of: new Map(), names: new Map() };
export function setTopics(of: ReadonlyMap<string, number>, names: ReadonlyMap<number, string>): void {
  TOPICS = { of, names };
}
/** A page without a vector has no topic: the neutral "none" colour, its own key row (sorted last). */
export const NO_TOPIC = "No vector";
const topicOf = (n: Pick<GNode, "id">): number | undefined => TOPICS.of.get(n.id);

/** Colourings with an order (little -> much): they take the neutral ramp, not a hue. */
export const RAMP_BY: ReadonlySet<ColorBy> = new Set(["depth", "degree", "evidence", "score", "recency", "added"]);
/** Continuous colourings: their legend is one gradient bar with its two ends named, never a list of swatches. */
export const BAR_BY: ReadonlySet<ColorBy> = new Set(["evidence", "score", "recency", "added"]);
const DAY_MS = 86_400_000;
/**
 * How fresh a date is, 0 (a year old or more) to 1 (this week); undefined without a date. It returns exactly the
 * ramp's `RAMP_STEPS` values (i / 4), so a node matches a step of the legend bar without the metric snap
 * (`rampStep`); colourDimensions.test.ts pins that.
 */
export function freshness(date: string | undefined | null, now: number = Date.now()): number | undefined {
  const at = date ? Date.parse(date) : NaN;
  if (Number.isNaN(at)) return undefined;
  const days = (now - at) / DAY_MS;
  return days <= 7 ? 1 : days <= 30 ? 0.75 : days <= 90 ? 0.5 : days <= 365 ? 0.25 : 0;
}
const DEPTH_T: Readonly<Record<string, number>> = { listed: 0, easy: 1 / 3, full: 2 / 3, deep: 1 };
/** How each depth reads in a colour key: a listed source was ingested but never digested. */
export const DEPTH_LABEL: Readonly<Record<string, string>> = { listed: "Ingest only", easy: "Easy digest", full: "Full digest", deep: "Deep digest" };
const depthOf = (n: GNode): string => n.depth || "listed";

/** The --bad status token, read once per theme: an ingested source nobody digested yet stands out on the ramp. */
const attention = new Map<string, string>();
function attentionColor(theme: string): string {
  const hit = attention.get(theme);
  if (hit) return hit;
  const bad = readCanvasColors().bad;
  if (!bad) return UNKNOWN_COLOR;          // the tokens are not there yet: read again next time
  attention.set(theme, bad);
  return bad;
}

/** Where the page sits on an ordered colouring, 0..1; undefined when the colouring does not apply to it. */
export function ordinalOf(n: GNode, by: ColorBy, metric?: number): number | undefined {
  switch (by) {
    case "depth":
      return n.layer === "source" ? DEPTH_T[n.depth || "listed"] : undefined;
    case "degree":
      return (3 - DEGREE_BANDS.indexOf(degreeBand(n))) / 3;
    case "evidence":
    case "score":
      return metric;
    case "recency":
      return freshness(n.changed || n.added);
    case "added":
      return freshness(n.added);
    default:
      return undefined;
  }
}

/** Steps of the ramp for a continuous signal (evidence, score): the legend bar draws the same five. */
export const RAMP_STEPS = 5;
export const rampStep = (t: number): number => Math.round(Math.max(0, Math.min(1, t)) * (RAMP_STEPS - 1)) / (RAMP_STEPS - 1);

/** What an ordered colouring measures, one line for the legend. */
export const RAMP_MEANING: Readonly<Partial<Record<ColorBy, { what: string; low: string; high: string }>>> = {
  evidence: { what: "How many digested sources back the page", low: "little", high: "much" },
  score: { what: "How central the page is (importance score)", low: "peripheral", high: "central" },
  depth: { what: "How deeply the source was read", low: "ingest only", high: "deep digest" },
  degree: { what: "How many links the page has", low: "few", high: "many" },
  recency: { what: "How recently the page changed", low: "a year or more", high: "this week" },
  added: { what: "When the page was added", low: "a year or more", high: "this week" },
};

/** Grey to black (light theme) or dim to white (dark) for a 0..1 signal: lightness, so it never fights the area hues. */
export function neutralRamp(t: number, dark: boolean): string {
  // ColorBrewer YlGnBu without its pale end (it vanishes on the grey canvas); the dark theme runs blue -> mint
  const stops = dark ? RAMP_DARK : RAMP_LIGHT;
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const a = stops[i]!;
  const b = stops[i + 1]!;
  const mix = (k: number) => Math.round(a[k]! + (b[k]! - a[k]!) * f);
  return `rgb(${mix(0)}, ${mix(1)}, ${mix(2)})`;
}
const hexRgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const RAMP_LIGHT = ["#7FCDBB", "#41B6C4", "#1D91C0", "#225EA8", "#0C2C84"].map(hexRgb);
const RAMP_DARK = ["#2B4C8C", "#2C7FB8", "#41B6C4", "#7FCDBB", "#D2F0B4"].map(hexRgb);

/**
 * `metric` is the 0..1 signal behind the evidence and score colourings (grey without one). `ramp` ("light" |
 * "dark") puts the ordered colourings on the neutral ramp instead of a hue (type is the mark: colour is the view's).
 */
export function colorOf(n: GNode, by: ColorBy, metric?: number, ramp?: "light" | "dark" | null, slots?: AreaSlots): string {
  if (ramp && RAMP_BY.has(by)) {
    // ingested but never digested is a state to act on, not the low end of the ramp: the status red
    if (by === "depth" && n.layer === "source" && depthOf(n) === "listed") return attentionColor(ramp);
    const t = ordinalOf(n, by, metric);
    // a continuous signal snaps to the legend bar's steps: neighbours stay apart, and the node matches its step
    return t === undefined ? UNKNOWN_COLOR : neutralRamp(METRIC_COLORS.has(by) ? rampStep(t) : t, ramp === "dark");
  }
  switch (by) {
    case "evidence":
    case "score":
      return metric === undefined ? UNKNOWN_COLOR : sequentialColor(metric);
    case "type":
    case "format":
      return typeColor(n.type);
    case "recency":
    case "added": {
      const t = ordinalOf(n, by);
      return t === undefined ? UNKNOWN_COLOR : sequentialColor(t);
    }
    case "support": {
      const s = supportOf(n);
      return s ? supportColor(s) : n.type === "person" ? PERSON_INK : UNKNOWN_COLOR;
    }
    case "layer":
      return layerColor(n.layer);
    case "depth":
      return n.layer === "source" ? depthColor(n.depth || "listed") : UNKNOWN_COLOR;
    case "status":
      return statusColor(n.maturity);
    case "area":
      return n.type === "person" && !n.areas[0] ? PERSON_INK : areaHue(areaOf(n, typeKeyed(slots ?? AREA_SLOT)), slots);
    case "degree":
      return degreeBand(n).color;
    case "topic": {
      const t = topicOf(n);
      return t === undefined ? NONE_GREY : topicColor(t);
    }
    default:
      return "#7aa2ff";
  }
}

/** The key a colour stands for, for the colour key shown when the colouring is not by type. */
export function colorKey(n: GNode, by: ColorBy, slots: AreaSlots = AREA_SLOT): string {
  switch (by) {
    case "evidence":
      return "Evidence: light = little, dark = much";
    case "score":
      return "Importance: light = low, dark = high";
    case "recency":
      return "Recency: light = old, dark = new";
    case "added":
      return "Date added: light = old, dark = new";
    case "support": {
      const s = supportOf(n);
      return s ? SUPPORT_LABEL[s] : n.type === "person" ? PEOPLE : "(not a concept)";
    }
    case "layer":
      return n.layer || "unknown";
    case "depth":
      return n.layer === "source" ? (DEPTH_LABEL[depthOf(n)] ?? depthOf(n)) : "(not a source)";
    case "status":
      return n.maturity || "(none)";
    case "area":
      if (n.type === "person" && !n.areas[0]) return PEOPLE;
      {
        const a = areaOf(n, typeKeyed(slots));
        return !a ? NO_AREA : slots.has(a) ? areaDisplay(a) : OTHER_AREAS;
      }
    case "degree":
      return degreeBand(n).label;
    case "topic": {
      const t = topicOf(n);
      return t === undefined ? NO_TOPIC : (TOPICS.names.get(t) ?? `Topic ${t + 1}`);
    }
    case "none":
      return "All pages";
    default:
      return n.type || "unknown";
  }
}

export interface SizeOptions {
  by: SizeBy;
  /** Base radius in graph units (the slider). */
  base: number;
  /** How much larger the biggest node gets in the tier/evidence/score/gap/logdeg modes (1 + range). */
  range?: number;
  /** Scale area perceptually (r ∝ v^0.57, Flannery) instead of linearly. */
  perceptual?: boolean;
  /** The 0..1 signal for the evidence/score/gap modes. */
  metric?: (n: GNode) => number;
}

const TIER_SIZE: Readonly<Record<number, number>> = { 1: 1, 2: 0.45, 3: 0 };
const tierOfType = (t: string) =>
  t === "topic" || t === "course" || t === "book" || t === "series" ? 1 : t === "idea" || t === "question" || t === "person" ? 2 : 3;
/** log(1 + links), 1 at 1400 links (the largest hub in the vault). */
const logDegree = (n: GNode) => Math.min(1, Math.log1p(degreeOf(n)) / Math.log1p(1400));

const metric = (n: GNode, by: SizeBy): number =>
  by === "in" ? n.inDegree || 0 : by === "out" ? n.outDegree || 0 : by === "connections" ? degreeOf(n) : 0;

/**
 * Radius in graph units. Degree maps through a square root so a few hubs do not swamp the rest
 * (0 links -> 0.6x, 24+ -> 1.6x), and a collection is drawn 1.5x as a hub over its members.
 */
export function nodeRadius(n: GNode, o: SizeOptions): number {
  if (o.by === "tier" || o.by === "logdeg" || METRIC_SIZES.has(o.by)) {
    let f = o.by === "tier" ? (TIER_SIZE[tierOfType(n.type)] ?? 0) : o.by === "logdeg" ? logDegree(n) : (o.metric?.(n) ?? 0);
    if (o.perceptual && f > 0) f = Math.pow(f, 0.57);
    return o.base * (1 + (o.range ?? 2.2) * Math.max(0, Math.min(1, f)));
  }
  const hub = n.layer === "collection" ? 1.5 : 1;
  if (o.by === "uniform") return o.base * hub;
  const d = Math.min(metric(n, o.by), 24);
  return o.base * (0.6 + Math.sqrt(d / 24)) * hub;
}

const median = (xs: number[]): number => {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)]!;
};
const SOURCE_LAYER = (n: GNode) => n.layer === "source";

/**
 * Radii by layer, each layer on its own scale. Sources keep the view's size signal (evidence) but stay
 * under the typical idea; concepts and people grow with their links instead, from a floor at the median paper,
 * so an idea is never smaller than a typical paper and a person never smaller than an idea; a topic is never
 * smaller than the largest idea. Rings get `RING_BOOST`.
 */
export function layeredRadii(nodes: readonly GNode[], o: SizeOptions): Map<string, number> {
  const src = new Map<string, number>();
  const con = new Map<string, number>();
  for (const n of nodes) {
    if (SOURCE_LAYER(n)) src.set(n.id, nodeRadius(n, o));
    else con.set(n.id, nodeRadius(n, { ...o, by: "logdeg" }));
  }
  const papers = nodes.filter((n) => n.type === "paper").map((n) => src.get(n.id) ?? 0);
  const floor = median(papers.length ? papers : [...src.values()]) || o.base;
  const lift = (r: number) => Math.max(r, floor);
  const ideas = nodes.filter((n) => n.type === "idea").map((n) => lift(con.get(n.id) ?? 0));
  const ideaMedian = median(ideas) || floor;
  const ideaMax = Math.max(floor, ...ideas);
  const out = new Map<string, number>();
  for (const n of nodes) {
    let r: number;
    if (SOURCE_LAYER(n)) r = Math.min(src.get(n.id) ?? floor, ideaMedian);
    else if (n.type === "topic") r = Math.max(con.get(n.id) ?? 0, ideaMax);
    else if (n.type === "person") r = Math.max(con.get(n.id) ?? 0, ideaMedian);
    else r = lift(con.get(n.id) ?? 0);
    const mark = markOf(n.type);
    out.set(n.id, mark === "source" || mark === "person" ? r : r * RING_BOOST);
  }
  return out;
}

/**
 * Semantic zoom: a node's screen size grows as zoom^gamma, not with the zoom, so zooming in opens space between
 * nodes instead of inflating them. `rGraph` is the layout radius (graph units), `scale` the current zoom and
 * `zr` the zoom relative to "fit"; the result is a radius in graph units for the current frame. The 5px floor
 * is on screen at fit, where it belongs.
 */
export const ZOOM_GAMMA = 0.5;
export function semanticRadius(rGraph: number, scale: number, zr: number): number {
  const kFit = scale / Math.max(zr, 1e-6);
  const pxAtFit = Math.max(rGraph * kFit, 5);
  return (pxAtFit * Math.pow(Math.max(zr, 1e-6), ZOOM_GAMMA)) / scale;
}

/** Type is the mark (./encoding), so colour by type would repeat the shape: such a view colours by area instead. */
/** A topic colouring without topics loaded (flag off, no embedding) colours by theme instead of all grey. */
export const effectiveColorBy = (by: ColorBy): ColorBy => (by === "type" || (by === "topic" && !TOPICS.of.size) ? "area" : by);
