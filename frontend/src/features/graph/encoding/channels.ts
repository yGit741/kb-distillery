import { colorKeyRows, type KeyRow } from "../legendModel";
import { colorOf, METRIC_COLORS, OTHER_GREY, RAMP_BY, RAMP_MEANING, type AreaSlots, type ColorBy, type SizeBy } from "../style";
import type { GNode } from "../types";

export type { KeyRow };

/**
 * A graph's colour channel: what colour answers on this surface, with the title its legend row shows ("Colour =
 * theme"). Every graph declares one; a surface may colour by anything, but never without saying what.
 */
export interface ColorChannel {
  by: string;
  /** what the colour means, lower case: "theme", "depth", "citation role" */
  title: string;
  color: (n: GNode) => string;
  /** the legend's swatches for these pages: value, colour, count */
  rows: (nodes: readonly GNode[]) => KeyRow[];
  /** an ordered colouring: the bar's two ends */
  ramp?: { low: string; high: string };
}

/** A graph's size channel, when node size varies: its legend row says "Size = links". */
export interface SizeChannel {
  by: string;
  title: string;
}

/** Each colouring's title, as the legend says it. */
export const COLOR_TITLE: Readonly<Record<ColorBy, string>> = {
  type: "type",
  layer: "layer",
  depth: "depth",
  status: "status",
  area: "theme",
  degree: "links",
  evidence: "evidence",
  score: "importance",
  none: "one colour",
};

/** Each size mode's title; uniform size is silent (no Size row). */
export const SIZE_TITLE: Readonly<Record<SizeBy, string | null>> = {
  tier: "type",
  evidence: "evidence",
  score: "importance",
  gap: "thin spot",
  logdeg: "links",
  connections: "links",
  in: "in-links",
  out: "out-links",
  uniform: null,
};

/**
 * The vault's colourings (./style colorOf) as a channel; `ramp` puts the ordered ones on the neutral ramp, `areas`
 * gives a surface its own area slots (`areaSlots`) instead of the Full Graph's.
 */
export function colorChannel(by: ColorBy, o: { ramp?: "light" | "dark" | null; metric?: (n: GNode) => number | undefined; limit?: number; areas?: AreaSlots } = {}): ColorChannel {
  const ramp = o.ramp ?? null;
  const meaning = ramp && RAMP_BY.has(by) ? RAMP_MEANING[by] : undefined;
  return {
    by,
    title: COLOR_TITLE[by],
    color: (n) => colorOf(n, by, METRIC_COLORS.has(by) ? o.metric?.(n) : undefined, ramp, o.areas),
    rows: (nodes) => colorKeyRows(nodes, new Set(nodes.map((n) => n.id)), by, o.limit ?? 12, ramp, o.areas),
    ramp: meaning ? { low: meaning.low, high: meaning.high } : undefined,
  };
}

/** A size mode as a channel; null when every node is one size. */
export function sizeChannel(by: SizeBy): SizeChannel | null {
  const title = SIZE_TITLE[by];
  return title ? { by, title } : null;
}

/** A channel of your own (citation role, ...): fixed values in a fixed order, each with its colour. */
export function fixedChannel<K extends string>(by: string, title: string, keyOf: (n: GNode) => K, values: readonly { key: K; label: string; color: string }[]): ColorChannel {
  const at = new Map(values.map((v) => [v.key, v]));
  return {
    by,
    title,
    color: (n) => at.get(keyOf(n))?.color ?? OTHER_GREY,
    rows: (nodes) => {
      const count = new Map<K, number>();
      for (const n of nodes) count.set(keyOf(n), (count.get(keyOf(n)) ?? 0) + 1);
      return values.filter((v) => count.get(v.key)).map((v) => ({ label: v.label, color: v.color, count: count.get(v.key)! }));
    },
  };
}
