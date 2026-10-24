import { areaColor, depthColor, layerColor, statusColor, typeColor, UNKNOWN_COLOR } from "@/theme/palette";
import { degreeOf, type GNode } from "./types";

export type ColorBy = "type" | "layer" | "depth" | "status" | "area" | "degree" | "evidence" | "score" | "none";
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
  { id: "evidence", label: "Evidence (digested sources)" },
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

/** `metric` is the 0..1 signal behind the evidence and score colourings (grey without one). */
export function colorOf(n: GNode, by: ColorBy, metric?: number): string {
  switch (by) {
    case "evidence":
    case "score":
      return metric === undefined ? UNKNOWN_COLOR : sequentialColor(metric);
    case "type":
      return typeColor(n.type);
    case "layer":
      return layerColor(n.layer);
    case "depth":
      return n.layer === "source" ? depthColor(n.depth || "listed") : UNKNOWN_COLOR;
    case "status":
      return statusColor(n.status);
    case "area":
      return areaColor(n.areas[0]);
    case "degree":
      return degreeBand(n).color;
    default:
      return "#7aa2ff";
  }
}

/** The key a colour stands for, for the colour key shown when the colouring is not by type. */
export function colorKey(n: GNode, by: ColorBy): string {
  switch (by) {
    case "evidence":
      return "Evidence: light = little, dark = much";
    case "score":
      return "Importance: light = low, dark = high";
    case "layer":
      return n.layer || "unknown";
    case "depth":
      return n.layer === "source" ? n.depth || "listed" : "(not a source)";
    case "status":
      return n.status || "(none)";
    case "area":
      return n.areas[0] || "(none)";
    case "degree":
      return degreeBand(n).label;
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
