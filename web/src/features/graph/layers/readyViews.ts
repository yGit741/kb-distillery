import type { ReadyView } from "@/api";
import { isParseError, parse, print } from "./grammar";
import type { GNode } from "../types";
import { FOCUS, newLayerId, type Layer } from "./model";
import { resolveNames } from "./names";
import { useLayers, type StackOp } from "./store";

/**
 * Views as layer stacks (flag graph-intent): ready views from the kit (lines of the query language the server only
 * passes on as text), pinned views written as `{ v: 2, layers, text }`. A ready view, a pinned view and a view typed
 * with `>` are the same object: an ordered stack of layers.
 */

export interface ReadyCard {
  id: string;
  name: string;
  description: string;
  /** The parsed stack; null when a line cannot be read here (the view then says it cannot run). */
  layers: Layer[] | null;
  /** The first line that could not be read, with the reason. */
  error?: string;
}

/** Read every line of a ready view with the grammar; one unreadable line makes the whole view unavailable. */
export function readyCard(v: Pick<ReadyView, "id" | "name" | "description" | "layers">): ReadyCard {
  const layers: Layer[] = [];
  for (const line of v.layers) {
    const l = parse(line);
    if (isParseError(l)) return { id: v.id, name: v.name, description: v.description, layers: null, error: `${line}: ${l.error}` };
    layers.push(l);
  }
  return { id: v.id, name: v.name, description: v.description, layers };
}

/** The same layers with fresh ids (a stack applied twice must not share ids). */
export const freshLayers = (layers: readonly Layer[]): Layer[] => layers.map((l) => ({ ...l, id: newLayerId() }));

const isLayer = (x: unknown): x is Layer => !!x && typeof x === "object" && typeof (x as Layer).kind === "string" && typeof (x as Layer).target === "string" && typeof (x as Layer).subgraph === "object";

/** The layers of a stored v2 spec, or null when the spec is not one (or holds no layer). */
export function specLayers(spec: Record<string, unknown>): Layer[] | null {
  if (spec.v !== 2 || !Array.isArray(spec.layers) || !spec.layers.length) return null;
  const layers = spec.layers.filter(isLayer);
  return layers.length === spec.layers.length ? freshLayers(layers) : null;
}

/** The text of a stack as one line per layer (what a pin or a recent step carries beside the layers). */
export const stackLines = (layers: readonly Layer[]): string[] => layers.map(print);

/** Apply layers to the screen's stack: `replace` (Enter) or `stack` (Shift+Enter). One undo step. */
export function applyLayers(op: Exclude<StackOp, "remove">, layers: readonly Layer[]): boolean {
  if (!layers.length) return false;
  return useLayers.getState().apply(op, freshLayers(layers));
}

/** A view whose layers name "the page in focus": it needs one page before it can run. */
export const isAnchored = (layers: readonly Layer[]): boolean => JSON.stringify(layers).includes(JSON.stringify(FOCUS));

/** The layers with the focus placeholder replaced by one page's slug. */
export const anchorLayers = (layers: readonly Layer[], nodes: readonly GNode[], slug: string): Layer[] => resolveNames([...layers], nodes, { focus: slug }).layers;
