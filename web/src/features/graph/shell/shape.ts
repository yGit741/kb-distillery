import type { ShapeResult, StyleSpec, StyleTarget } from "@/api";
import { useKb } from "@/lib/store";
import type { GraphView } from "../pageSearch";
import { useGraphUi, type GraphUiState } from "../store";
import type { ColorBy, SizeBy } from "../style";
import type { GNode } from "../types";
import { cellIds, slugResolver } from "../tools/QueryPanel";

/**
 * Free-text shaping (flag graph-shell): what `POST /api/graph/shape` answers, mapped onto the graph's own knobs.
 * Rows become the drawn pages; the style clauses drive the colour, size, layout and hidden types the screen already
 * has. A clause the graph cannot draw is listed back as "not applied" (with the reason), never dropped silently.
 */

/** The knobs a shape may change, and so what one level of undo gives back. */
type Knobs = Pick<GraphUiState, "view" | "shownTypes" | "colorBy" | "sizeBy" | "layoutMode" | "story" | "hiddenKeys" | "hiddenLinkKinds">;

export interface Snapshot extends Knobs {
  selection: readonly string[];
}

export function snapshot(): Snapshot {
  const s = useGraphUi.getState();
  return {
    view: s.view,
    shownTypes: s.shownTypes,
    colorBy: s.colorBy,
    sizeBy: s.sizeBy,
    layoutMode: s.layoutMode,
    story: s.story,
    hiddenKeys: s.hiddenKeys,
    hiddenLinkKinds: s.hiddenLinkKinds,
    selection: [...useKb.getState().selection],
  };
}

export function restore(snap: Snapshot): void {
  const { selection, ...knobs } = snap;
  useGraphUi.setState(knobs);
  useKb.getState().setSelection([...selection]);
  useGraphUi.getState().fit();
}

/** The pieces of a snapshot a later change by hand would replace: while all still hold, the shape is still what is drawn. */
export type Marker = Pick<Knobs, "view" | "shownTypes" | "colorBy" | "sizeBy" | "layoutMode" | "hiddenLinkKinds">;
export const marker = (s: Marker = useGraphUi.getState()): Marker => ({
  view: s.view,
  shownTypes: s.shownTypes,
  colorBy: s.colorBy,
  sizeBy: s.sizeBy,
  layoutMode: s.layoutMode,
  hiddenLinkKinds: s.hiddenLinkKinds,
});
export const sameMarker = (a: Marker, b: Marker) => (Object.keys(a) as (keyof Marker)[]).every((k) => a[k] === b[k]);

// ---- rows -> pages
/** The page ids a result names: every cell that is a page slug (or a path's list of them), once, in row order. */
export function shapeIds(res: Pick<ShapeResult, "rows">, byId: ReadonlyMap<string, GNode>): string[] {
  const resolve = slugResolver(byId);
  return [...new Set(res.rows.flatMap((r) => r.flatMap((c) => cellIds(c, resolve))))];
}

// ---- style -> knobs
const COLOUR_PROP: Readonly<Record<string, ColorBy>> = { layer: "layer", depth: "depth", maturity: "status", areas: "area" };
const SKIP_COLOUR_TYPE = "the mark already shows the type";

/** The graph's edge kinds (kb_distillery.graph.model) -> the link kinds the canvas draws (`GLink.kind`). */
const LINK_KINDS: Readonly<Record<string, readonly string[]>> = { MENTIONS: ["wikilink", "related"], BOOK: ["book"], SHARES_SOURCE: ["shared"] };

export interface StylePlan {
  patch: Partial<Pick<GraphUiState, "colorBy" | "sizeBy" | "layoutMode">>;
  /** Types to take out of the drawn set (a hidden node label). */
  hideTypes: string[];
  /** Link kinds of the graph model to draw off (`hide MENTIONS`). */
  hideLinkKinds: string[];
  /** Clauses the graph cannot draw, with the reason: "colour by year". */
  skipped: string[];
}

const kebab = (label: string) => label.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();

/**
 * A node label of the Cypher graph (`Paper`, `AiChat`, or a layer: `Source`) -> the page types of this graph it names.
 * The types come from the graph itself: a kit may have types the base model does not (`Company`).
 */
export function typesOfLabel(label: string, nodes: Iterable<Pick<GNode, "type" | "layer">>): string[] {
  const k = kebab(label);
  const out = new Set<string>();
  for (const n of nodes) if (n.type === k || n.layer === k) out.add(n.type);
  return [...out];
}

const propName = (t: StyleTarget) => (t.by === "prop" ? (t.name ?? "") : t.by);

export function planStyle(style: StyleSpec, nodes: Iterable<Pick<GNode, "type" | "layer">>): StylePlan {
  const patch: StylePlan["patch"] = {};
  const hideTypes: string[] = [];
  const hideLinkKinds: string[] = [];
  const skipped: string[] = [];
  const all = [...nodes];

  if (style.layout) {
    if (style.layout === "force") patch.layoutMode = "free";
    else if (style.layout === "radial") patch.layoutMode = "anchored";
    else skipped.push(`layout ${style.layout} (not drawn yet)`);
  }
  if (style.group_by) {
    const g = style.group_by;
    // the anchored layout gathers pages by their area: the one grouping the graph has
    // (radial maps to the same layout: the anchored one puts topics on a ring)
    if (g.by === "prop" && g.name === "areas") patch.layoutMode = "anchored";
    else skipped.push(`group by ${propName(g)} (only areas gather pages)`);
  }
  if (style.colour_by) {
    const c = style.colour_by;
    const by: ColorBy | undefined = c.by === "degree" ? "degree" : c.by === "prop" ? COLOUR_PROP[c.name ?? ""] : undefined;
    if (by) patch.colorBy = by;
    else skipped.push(`colour by ${propName(c)} (${c.by === "label" || c.name === "type" ? SKIP_COLOUR_TYPE : "not drawn yet"})`);
  }
  if (style.size_by) {
    const s = style.size_by;
    const by: SizeBy | undefined = s.by === "degree" ? "connections" : undefined;
    if (by) patch.sizeBy = by;
    else skipped.push(`size by ${propName(s)} (only links size the pages)`);
  }
  for (const label of style.hide_labels) {
    const types = typesOfLabel(label, all);
    if (types.length) hideTypes.push(...types);
    else skipped.push(`hide ${label} (no such kind of page)`);
  }
  for (const kind of style.hide_edge_kinds) {
    const kinds = LINK_KINDS[kind];
    if (kinds) hideLinkKinds.push(...kinds);
    else skipped.push(`hide ${kind} (links of that kind are not drawn apart)`);
  }
  if (style.label) skipped.push(`label ${style.label} (pages show their title)`);
  return { patch, hideTypes, hideLinkKinds, skipped };
}

/** The view without the pages of some types (a view draws its pages past the type filter, so a hidden type must leave it). */
export function dropTypes(view: GraphView, types: ReadonlySet<string>, byId: ReadonlyMap<string, GNode>): GraphView | null {
  const keep = (id: string) => !types.has(byId.get(id)?.type ?? "");
  const hits = new Set([...view.hits].filter(keep));
  return hits.size ? { ...view, hits, shown: new Set([...view.shown].filter(keep)) } : null;
}

/** What the status pill says: the canonical style, else the pages. */
export function pillText(styleText: string, pages: number | null): string {
  const parts = [styleText.trim().replace(/\s*;\s*/g, "; "), pages === null ? "" : `${pages} page${pages === 1 ? "" : "s"}`].filter(Boolean);
  return parts.join(" · ");
}
