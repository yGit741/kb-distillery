import type { NeighborMap } from "./graphData";

export interface Focus {
  /** Selected and hovered ids: drawn at full strength. */
  core: ReadonlySet<string>;
  /** core plus their neighbours: drawn, the rest dims. */
  lit: ReadonlySet<string>;
  /** Opacity of the rest; 0.12 when absent. */
  dim?: number;
}

/** The neighbourhood highlight: only a selection dims the rest; a hover then joins it. null = nothing dims. */
export function computeFocus(
  selected: ReadonlySet<string>,
  hovered: string | null,
  neighbors: NeighborMap,
  enabled: boolean,
): Focus | null {
  if (!enabled || !selected.size) return null;
  const core = new Set(selected);
  if (hovered) core.add(hovered);
  const lit = new Set(core);
  core.forEach((id) => (neighbors.get(id) ?? []).forEach((n) => lit.add(n)));
  return { core, lit };
}

export function nodeOpacity(id: string, focus: Focus | null): number {
  if (!focus || focus.core.has(id)) return 1;
  return focus.lit.has(id) ? 0.95 : focus.dim ?? 0.12;
}

/** Same core and dim = same look: a recompute that changes neither must not restart a fade. */
export const focusKey = (f: Focus | null): string => (f ? `${[...f.core].sort().join("|")}@${f.dim ?? 0.12}@${f.lit.size}` : "");

const ease = (t: number) => 1 - (1 - t) * (1 - t);

/** Cross-fade from the previous focus to the current one, `t` 0..1. The focus itself shows at once
 *  (a static highlight); only the rest fades, so A → B never flashes back to the unfocused graph. */
export function fadedNodeOpacity(id: string, focus: Focus | null, prev: Focus | null, t: number): number {
  const now = nodeOpacity(id, focus);
  if (!prev || t >= 1 || focus?.lit.has(id)) return now;
  const was = nodeOpacity(id, prev);
  return was + (now - was) * ease(t);
}

export function fadedLinkOpacity(
  source: string,
  target: string,
  focus: Focus | null,
  prev: Focus | null,
  t: number,
  base: number,
  kind: string,
): number {
  const now = linkOpacity(source, target, focus, base, kind);
  if (!prev || t >= 1) return now;
  const was = linkOpacity(source, target, prev, base, kind);
  return was + (now - was) * ease(t);
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
  return b * ((focus.dim ?? 0.12) < 0.2 ? 0.15 : 0.4);
}
