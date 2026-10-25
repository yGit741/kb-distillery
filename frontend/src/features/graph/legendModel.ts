import { DEPTHS, LAYERS, type Layer } from "@/api/model";
import { colorKey, colorOf, NO_AREA, ordinalOf, OTHER_AREAS, PEOPLE, RAMP_BY, type ColorBy } from "./style";
import { presentTypes, type GraphSchema, type TypeInfo } from "./schema";
import type { GNode } from "./types";

export const LAYER_LABEL: Record<Layer, string> = { source: "Sources", collection: "Collections", concept: "Concepts" };

export interface TypeRow extends TypeInfo {
  total: number;
  visible: number;
  shown: boolean;
}

export interface LayerGroup {
  layer: Layer;
  rows: TypeRow[];
  total: number;
  /** all | some | none of its types are drawn */
  state: "all" | "some" | "none";
}

/** Layer -> type rows with counts. `shownTypes === null` means every type is on. */
export function layerGroups(
  nodes: readonly GNode[],
  visible: ReadonlySet<string>,
  schema: GraphSchema,
  shownTypes: ReadonlySet<string> | null,
): LayerGroup[] {
  const total = new Map<string, number>();
  const vis = new Map<string, number>();
  for (const n of nodes) {
    total.set(n.type, (total.get(n.type) ?? 0) + 1);
    if (visible.has(n.id)) vis.set(n.type, (vis.get(n.type) ?? 0) + 1);
  }
  const rows: TypeRow[] = presentTypes(schema, [...total.keys()]).map((t) => ({
    ...t,
    total: total.get(t.id) ?? 0,
    visible: vis.get(t.id) ?? 0,
    shown: !shownTypes || shownTypes.has(t.id),
  }));
  return LAYERS.map((layer) => {
    const mine = rows.filter((r) => r.layer === layer);
    const on = mine.filter((r) => r.shown).length;
    return {
      layer,
      rows: mine,
      total: mine.reduce((s, r) => s + r.total, 0),
      state: on === 0 ? ("none" as const) : on === mine.length ? ("all" as const) : ("some" as const),
    };
  }).filter((g) => g.rows.length);
}

export interface DepthRow {
  depth: string;
  total: number;
  shown: boolean;
}

/** How many sources sit at each depth (listed -> deep). */
export function depthRows(nodes: readonly GNode[], shownDepths: ReadonlySet<string> | null): DepthRow[] {
  const total = new Map<string, number>();
  for (const n of nodes) if (n.layer === "source") total.set(n.depth || "listed", (total.get(n.depth || "listed") ?? 0) + 1);
  return DEPTHS.map((depth) => ({ depth, total: total.get(depth) ?? 0, shown: !shownDepths || shownDepths.has(depth) }));
}

export interface KeyRow {
  label: string;
  color: string;
  count: number;
  /** position on an ordered colouring (ramp rows sort by it, light to dark) */
  t?: number;
}

/**
 * The colour key for any colouring but "type" (there the legend rows are the key): most common first, or
 * light to dark on the neutral ramp (`ramp`). Hidden keys still count, so a filtered-out row stays clickable.
 */
export function colorKeyRows(nodes: readonly GNode[], visible: ReadonlySet<string>, by: ColorBy, limit = 10, ramp: "light" | "dark" | null = null): KeyRow[] {
  const rows = new Map<string, KeyRow>();
  for (const n of nodes) {
    if (!visible.has(n.id)) continue;
    const label = colorKey(n, by);
    const r = rows.get(label) ?? { label, color: colorOf(n, by, undefined, ramp), count: 0, t: ordinalOf(n, by) };
    r.count += 1;
    rows.set(label, r);
  }
  const ordered = ramp && RAMP_BY.has(by);
  // the catch-all rows ("Other areas", "No area") close the list whatever their counts
  const last = (r: KeyRow) => (r.label === PEOPLE ? 1 : r.label === OTHER_AREAS ? 2 : r.label === NO_AREA ? 3 : 0);
  const sorted = [...rows.values()].sort(
    (a, b) => last(a) - last(b) || (ordered ? (a.t ?? 2) - (b.t ?? 2) : b.count - a.count) || a.label.localeCompare(b.label),
  );
  // the limit trims the real values only, so the catch-alls are never cut off
  return [...sorted.filter((r) => !last(r)).slice(0, limit), ...sorted.filter((r) => last(r))];
}
