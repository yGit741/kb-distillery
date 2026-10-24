import { areaColor, depthColor, layerColor, statusColor, typeColor, UNKNOWN_COLOR } from "@/theme/palette";
import { degreeOf, type GNode } from "./types";

export type ColorBy = "type" | "layer" | "depth" | "status" | "area" | "degree" | "none";
export type SizeBy = "connections" | "in" | "out" | "uniform";

export const COLOR_BY: readonly { id: ColorBy; label: string }[] = [
  { id: "type", label: "Type" },
  { id: "layer", label: "Layer" },
  { id: "depth", label: "Depth (sources)" },
  { id: "status", label: "Status" },
  { id: "area", label: "Primary area" },
  { id: "degree", label: "Link count" },
  { id: "none", label: "One colour" },
];

export const SIZE_BY: readonly { id: SizeBy; label: string }[] = [
  { id: "connections", label: "Connections (in + out)" },
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

export function colorOf(n: GNode, by: ColorBy): string {
  switch (by) {
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
}

const metric = (n: GNode, by: SizeBy): number =>
  by === "in" ? n.inDegree || 0 : by === "out" ? n.outDegree || 0 : by === "connections" ? degreeOf(n) : 0;

/**
 * Radius in graph units. Degree maps through a square root so a few hubs do not swamp the rest
 * (0 links -> 0.6x, 24+ -> 1.6x), and a collection is drawn 1.5x as a hub over its members.
 */
export function nodeRadius(n: GNode, o: SizeOptions): number {
  const hub = n.layer === "collection" ? 1.5 : 1;
  if (o.by === "uniform") return o.base * hub;
  const d = Math.min(metric(n, o.by), 24);
  return o.base * (0.6 + Math.sqrt(d / 24)) * hub;
}
