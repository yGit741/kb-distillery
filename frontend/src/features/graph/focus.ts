import type { NeighborMap } from "./graphData";

export interface Focus {
  /** Selected and hovered ids: drawn at full strength. */
  core: ReadonlySet<string>;
  /** core plus their neighbours: drawn, the rest dims. */
  lit: ReadonlySet<string>;
}

/** The neighbourhood highlight covers the selection and the hovered node together; null = nothing dims. */
export function computeFocus(
  selected: ReadonlySet<string>,
  hovered: string | null,
  neighbors: NeighborMap,
  enabled: boolean,
): Focus | null {
  if (!enabled || (!hovered && !selected.size)) return null;
  const core = new Set(selected);
  if (hovered) core.add(hovered);
  const lit = new Set(core);
  core.forEach((id) => (neighbors.get(id) ?? []).forEach((n) => lit.add(n)));
  return { core, lit };
}

export function nodeOpacity(id: string, focus: Focus | null): number {
  if (!focus || focus.core.has(id)) return 1;
  return focus.lit.has(id) ? 0.95 : 0.12;
}

export function linkOpacity(
  source: string,
  target: string,
  focus: Focus | null,
  base: number,
  kind: string,
): number {
  const b = base * (kind === "shared" ? 0.6 : 1);
  if (!focus) return b;
  if (focus.core.has(source) || focus.core.has(target)) return Math.min(b + 0.35, 0.95);
  return b * 0.15;
}
