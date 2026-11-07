import type { StyleSpec } from "@/api";
import type { ViewSpecV1 } from "../shell/corners/viewSpec";
import { LINE_COPY } from "../shell/copy";
import { LINK_KINDS, planStyle } from "../shell/shape";
import type { ColorBy, SizeBy } from "../style";
import type { GLink, GNode } from "../types";

/**
 * The layer model (flag graph-intent): a view is an ordered stack of layers, each one a show, hide or style applied to
 * a subgraph. Pure types and helpers, no React. `evaluate` folds a stack onto the graph's existing knobs.
 */

export type Op = ">=" | ">" | "<=" | "<" | "=";

/** One condition on pages. All conditions of a subgraph must hold. */
export type NodeCond =
  | { t: "type"; value: string | string[] }
  | { t: "degree"; op: Op; n: number }
  | { t: "hops"; of: string; n: number }
  | { t: "name"; slugs: string[] }
  | { t: "text"; phrase: string }
  | { t: "favorite" }
  /** Pages close in meaning to `phrase`. `slugs` is the answer of the meaning service (filled in before the layer is applied, see meaning.ts); `slug` marks "similar to this": the page whose own card asked. */
  | { t: "about"; phrase: string; slug?: string; slugs?: string[] }
  | { t: "inArea"; area: string }
  | { t: "createdWithin"; days: number }
  | { t: "linkedFromType"; type: string }
  /** Pages on a path of at most `n` hops between two pages. */
  | { t: "paths"; a: string; b: string; n: number }
  /** Pages with (or, `exists: false`, without) a link of this type. */
  | { t: "hasEdge"; type: string; exists?: false }
  | { t: "mentionedIn"; chat: string }
  | { t: "not"; cond: NodeCond }
  | { t: "all" };

/** In `hops.of`: the favorites as a whole, and the page in focus (filled in before the layer is applied). */
export const FAVORITES = "$favorites";
export const FOCUS = "$focus";

/** One condition on links. */
export type EdgeCond =
  | { t: "type"; value: string }
  | { t: "direction"; value: "in" | "out" | "both" }
  | { t: "endpoints"; slugs: string[] }
  | { t: "count"; op: Op; n: number }
  | { t: "all" };

export interface Subgraph {
  nodes?: NodeCond[];
  edges?: EdgeCond[];
}

export interface LayerStyle {
  color?: ColorBy | { by: string };
  size?: SizeBy | { by: string };
  width?: "thin" | "normal" | "thick" | { by: string };
  label?: string;
}

export interface Layer {
  id: string;
  kind: "show" | "hide" | "style";
  target: "nodes" | "edges";
  subgraph: Subgraph;
  style?: LayerStyle;
  /** Plain words for the chip; `describe` fills it in when empty. */
  text: string;
  /** A V1 pinned view carried as one layer: applying it reuses `applySpec`. */
  legacy?: ViewSpecV1;
}

export interface ViewStack {
  v: 2;
  layers: Layer[];
}

export const EMPTY_STACK: ViewStack = { v: 2, layers: [] };

let counter = 0;
/** A fresh layer id. */
export const newLayerId = (): string => `L${++counter}`;

export function makeLayer(kind: Layer["kind"], target: Layer["target"], subgraph: Subgraph, text = "", extra: Partial<Pick<Layer, "style" | "legacy">> = {}): Layer {
  return { id: newLayerId(), kind, target, subgraph, text, ...extra };
}

// ---- operations (pure)
const isStyle = (l: Layer) => l.kind === "style";

/** `>`: the show/hide layers are replaced, the style layers stay. */
export const replace = (vs: ViewStack, layers: Layer[]): ViewStack => ({ v: 2, layers: [...vs.layers.filter(isStyle), ...layers] });

/** `>+`: the new layers go on top; a later layer wins on conflict. */
export const stack = (vs: ViewStack, layers: Layer[]): ViewStack => ({ v: 2, layers: [...vs.layers, ...layers] });

const norm = (s: string) => s.trim().toLowerCase();

/** `>-`: the first layer whose id or chip text matches goes; no match returns the same stack. */
export function remove(vs: ViewStack, textOrId: string): ViewStack {
  const k = norm(textOrId);
  const i = vs.layers.findIndex((l) => l.id === textOrId || norm(l.text) === k || norm(describe(l)) === k);
  return i < 0 ? vs : { v: 2, layers: vs.layers.filter((_, j) => j !== i) };
}

/** Change one layer where it stands (the chip's popover). */
export const update = (vs: ViewStack, id: string, layer: Layer): ViewStack => ({ v: 2, layers: vs.layers.map((l) => (l.id === id ? layer : l)) });

// ---- words
const linksWord = (n: number) => `${n} link${n === 1 ? "" : "s"}`;
const OP_WORDS: Record<Op, (n: number) => string> = {
  ">=": (n) => `at least ${linksWord(n)}`,
  ">": (n) => `more than ${linksWord(n)}`,
  "<=": (n) => `at most ${linksWord(n)}`,
  "<": (n) => `fewer than ${linksWord(n)}`,
  "=": (n) => `exactly ${linksWord(n)}`,
};

export function describeNodeCond(c: NodeCond): string {
  switch (c.t) {
    case "type":
      return `type ${Array.isArray(c.value) ? c.value.join(" or ") : c.value}`;
    case "degree":
      return OP_WORDS[c.op](c.n);
    case "hops":
      return `within ${c.n} hop${c.n === 1 ? "" : "s"} of ${c.of === FAVORITES ? "favorites" : c.of === FOCUS ? "this page" : c.of}`;
    case "paths":
      return `paths between ${c.a} and ${c.b} up to ${c.n} hops`;
    case "hasEdge":
      return c.exists === false ? `without a ${c.type} link` : `with a ${c.type} link`;
    case "mentionedIn":
      return `mentioned in chat "${c.chat}"`;
    case "not":
      return `not ${describeNodeCond(c.cond)}`;
    case "name":
      return c.slugs.join(", ");
    case "text":
      return `mentioning "${c.phrase}"`;
    case "favorite":
      return "favorites";
    case "about":
      return `about "${c.phrase}"`;
    case "inArea":
      return `in area ${c.area}`;
    case "createdWithin":
      return `added in the last ${c.days} day${c.days === 1 ? "" : "s"}`;
    case "linkedFromType":
      return `linked from a ${c.type}`;
    case "all":
      return "all pages";
  }
}

export function describeEdgeCond(c: EdgeCond): string {
  switch (c.t) {
    case "type":
      return `${c.value} links`;
    case "direction":
      return c.value === "both" ? "either direction" : c.value === "in" ? "incoming" : "outgoing";
    case "endpoints":
      return `between ${c.slugs.join(" and ")}`;
    case "count":
      return `${OP_WORDS[c.op](c.n).replace(/ links?$/, "")} between a pair`;
    case "all":
      return "all links";
  }
}

const styleWord = (v: unknown) => (typeof v === "string" ? v : v && typeof v === "object" && "by" in v ? `by ${String((v as { by: string }).by)}` : "");

/** Plain words for a layer: its own text when it has one. */
export function describe(layer: Layer): string {
  if (layer.text.trim()) return layer.text;
  const target = layer.target === "nodes" ? "pages" : "links";
  const conds = layer.target === "nodes" ? (layer.subgraph.nodes ?? []).map(describeNodeCond) : (layer.subgraph.edges ?? []).map(describeEdgeCond);
  if (layer.kind === "style") {
    const s = layer.style ?? {};
    const parts = [s.color !== undefined && `colour ${styleWord(s.color)}`, s.size !== undefined && `size ${styleWord(s.size)}`, s.width !== undefined && `width ${styleWord(s.width)}`, s.label && `label ${s.label}`].filter(Boolean);
    const head = `Style ${target}${parts.length ? `: ${parts.join(", ")}` : ""}`;
    return conds.length ? `${head} for ${conds.join(", ")}` : head;
  }
  const verb = layer.kind === "show" ? "Show" : "Hide";
  return conds.length ? `${verb} ${target}: ${conds.join(", ")}` : `${verb} all ${target}`;
}

// ---- V1 pinned views
/** A V1 pinned view as one `show` layer: its name is the chip, its spec rides along and applies through `applySpec`. */
export function fromViewSpecV1(spec: ViewSpecV1, name: string): ViewStack {
  return { v: 2, layers: [makeLayer("show", "nodes", {}, name.trim() || "Pinned view", { legacy: spec })] };
}

// ---- evaluation
export interface EvalGraph {
  nodes: readonly GNode[];
  links: readonly Pick<GLink, "source" | "target" | "kind">[];
  /** Page ids marked favorite; absent while favorites are not loaded. */
  favorites?: ReadonlySet<string>;
  now?: number;
}

/** The knobs a stack may change (a patch for the graph store). */
export interface KnobPatch {
  colorBy?: ColorBy;
  sizeBy?: SizeBy;
  layoutMode?: "free" | "anchored";
}

export interface LegendRow {
  /** Which layer the row comes from. */
  id: string;
  group: "pages" | "links";
  label: string;
}

export interface Evaluation {
  /** The pages drawn; null = no restriction. */
  nodeIds: Set<string> | null;
  /** Link kinds of the canvas drawn off. */
  hiddenLinkKinds: Set<string>;
  patch: KnobPatch;
  /** Conditions and clauses the graph cannot evaluate or draw yet, with the reason: never dropped silently. */
  skipped: string[];
  legend: LegendRow[];
}

const cmp = (v: number, op: Op, n: number) => (op === ">=" ? v >= n : op === ">" ? v > n : op === "<=" ? v <= n : op === "<" ? v < n : v === n);

function adjacency(links: EvalGraph["links"]): Map<string, Set<string>> {
  const adj = new Map<string, Set<string>>();
  const add = (a: string, b: string) => {
    let s = adj.get(a);
    if (!s) adj.set(a, (s = new Set()));
    s.add(b);
  };
  for (const l of links) {
    if (l.source === l.target) continue;
    add(l.source, l.target);
    add(l.target, l.source);
  }
  return adj;
}

/** Pages within `n` hops of `from` (itself included), over links in either direction. */
export function withinHops(adj: ReadonlyMap<string, ReadonlySet<string>>, from: string, n: number): Set<string> {
  const seen = new Set([from]);
  let edge = [from];
  for (let d = 0; d < n && edge.length; d++) {
    const next: string[] = [];
    for (const id of edge)
      for (const o of adj.get(id) ?? [])
        if (!seen.has(o)) {
          seen.add(o);
          next.push(o);
        }
    edge = next;
  }
  return seen;
}

/** Hops from `from` to every page within `max` hops, over links in either direction. */
function distances(adj: ReadonlyMap<string, ReadonlySet<string>>, from: string, max: number): Map<string, number> {
  const dist = new Map([[from, 0]]);
  let edge = [from];
  for (let d = 1; d <= max && edge.length; d++) {
    const next: string[] = [];
    for (const id of edge)
      for (const o of adj.get(id) ?? [])
        if (!dist.has(o)) {
          dist.set(o, d);
          next.push(o);
        }
    edge = next;
  }
  return dist;
}

/** The graph kinds (`MENTIONS`) and the canvas kinds (`wikilink`) a layer's link type may name. */
function linkKindsOf(value: string, present: ReadonlySet<string>): string[] | null {
  const mapped = LINK_KINDS[value.toUpperCase()];
  if (mapped) return [...mapped];
  const k = value.toLowerCase();
  return present.has(k) ? [k] : null;
}

const toStyleSpec = (s: LayerStyle): StyleSpec => {
  const spec: StyleSpec = { hide_edge_kinds: [], hide_labels: [] };
  const by = (v: { by: string }) => (v.by === "degree" ? ({ by: "degree" } as const) : ({ by: "prop", name: v.by } as const));
  if (s.color && typeof s.color === "object") spec.colour_by = by(s.color);
  if (s.size && typeof s.size === "object") spec.size_by = by(s.size);
  return spec;
};

export function evaluate(vs: ViewStack, graph: EvalGraph): Evaluation {
  const { nodes, links } = graph;
  const all = new Set(nodes.map((n) => n.id));
  const byId = new Map(nodes.map((n) => [n.id, n] as const));
  const adj = adjacency(links);
  const now = graph.now ?? Date.now();
  const presentKinds = new Set<string>(links.map((l) => l.kind));
  const skipped: string[] = [];
  let skips = 0;
  const skip = (s: string) => {
    skips++;
    if (!skipped.includes(s)) skipped.push(s);
  };
  const pageOf = (of: string) => (byId.has(of) ? of : [...byId.values()].find((n) => n.title.toLowerCase() === of.toLowerCase())?.id);

  let cur: Set<string> | null = null;
  let hiddenKinds: Set<string> | null = null;
  let shownKinds: Set<string> | null = null;
  const patch: KnobPatch = {};
  const legend: LegendRow[] = [];

  const matchNodes = (conds: NodeCond[] | undefined, label: string): Set<string> => {
    let out = new Set(all);
    for (const c of conds ?? []) {
      let keep: (n: GNode) => boolean;
      switch (c.t) {
        case "all":
          continue;
        case "type": {
          const t = new Set(Array.isArray(c.value) ? c.value : [c.value]);
          keep = (n) => t.has(n.type) || t.has(n.layer);
          break;
        }
        case "degree":
          keep = (n) => cmp(adj.get(n.id)?.size ?? 0, c.op, c.n);
          break;
        case "hops": {
          if (c.of === FAVORITES) {
            if (!graph.favorites) {
              skip(`${label}: favorites (not loaded here yet)`);
              continue;
            }
            const near = new Set<string>();
            for (const f of graph.favorites) if (byId.has(f)) withinHops(adj, f, c.n).forEach((id) => near.add(id));
            keep = (n) => near.has(n.id);
            break;
          }
          const from = c.of === FOCUS ? undefined : pageOf(c.of);
          if (!from) {
            skip(c.of === FOCUS ? `${label}: no page is in focus` : `${label}: "${c.of}" is not a page here`);
            continue;
          }
          const near = withinHops(adj, from, c.n);
          keep = (n) => near.has(n.id);
          break;
        }
        case "paths": {
          const a = pageOf(c.a);
          const b = pageOf(c.b);
          if (!a || !b) {
            skip(`${label}: "${a ? c.b : c.a}" is not a page here`);
            continue;
          }
          const da = distances(adj, a, c.n);
          const db = distances(adj, b, c.n);
          keep = (n) => (da.get(n.id) ?? Infinity) + (db.get(n.id) ?? Infinity) <= c.n;
          break;
        }
        case "hasEdge":
          skip(`${label}: links of type ${c.type} (the types of links are not known to the canvas yet)`);
          continue;
        case "mentionedIn":
          skip(`${label}: mentioned in a chat (not available yet)`);
          continue;
        case "not": {
          const before = skips;
          const inner = matchNodes([c.cond], label);
          if (skips > before) continue;
          keep = (n) => !inner.has(n.id);
          break;
        }
        case "name": {
          const s = new Set(c.slugs);
          keep = (n) => s.has(n.id);
          break;
        }
        case "inArea":
          keep = (n) => n.areas.includes(c.area);
          break;
        case "createdWithin":
          keep = (n) => {
            const t = Date.parse(n.added);
            return Number.isFinite(t) && now - t <= c.days * 86_400_000;
          };
          break;
        case "linkedFromType": {
          const from = new Set<string>();
          for (const l of links) if (byId.get(l.source)?.type === c.type) from.add(l.target);
          keep = (n) => from.has(n.id);
          break;
        }
        case "favorite":
          if (!graph.favorites) {
            skip(`${label}: favorites (not loaded here yet)`);
            continue;
          }
          keep = (n) => graph.favorites!.has(n.id);
          break;
        case "about": {
          if (!c.slugs) {
            skip(`${label}: about "${c.phrase}" (${LINE_COPY.meaningOff})`);
            continue;
          }
          const near = new Set(c.slugs);
          keep = (n) => near.has(n.id);
          break;
        }
        case "text":
          skip(`${label}: mentioning "${c.phrase}" (text search is not available yet)`);
          continue;
      }
      out = new Set([...out].filter((id) => keep(byId.get(id)!)));
    }
    return out;
  };

  for (const layer of vs.layers) {
    const label = describe(layer);
    if (layer.legacy) continue; // applied by applySpec, not by the fold
    if (layer.kind === "style") {
      const s = layer.style ?? {};
      const scoped = (layer.subgraph.nodes ?? []).some((c) => c.t !== "all") || (layer.subgraph.edges ?? []).some((c) => c.t !== "all");
      if (layer.target === "nodes") {
        if (s.color !== undefined || s.size !== undefined) {
          const plan = planStyle(toStyleSpec(s), nodes);
          if (typeof s.color === "string") patch.colorBy = s.color;
          if (typeof s.size === "string") patch.sizeBy = s.size;
          Object.assign(patch, plan.patch);
          plan.skipped.forEach(skip);
          if (scoped) skip(`${label}: the style applies to every page (per-page style is not drawn yet)`);
          legend.push({ id: layer.id, group: "pages", label });
        }
        if (s.label) skip(`${label}: labels (pages show their title)`);
      } else {
        if (s.width !== undefined) skip(`${label}: link width (not drawn yet)`);
        if (s.color !== undefined) skip(`${label}: link colour (not drawn yet)`);
        legend.push({ id: layer.id, group: "links", label });
      }
      continue;
    }
    if (layer.target === "nodes") {
      const m = matchNodes(layer.subgraph.nodes, label);
      if (layer.kind === "show") cur = cur === null ? m : new Set([...cur, ...m]);
      else {
        const base: Set<string> = cur ?? new Set(all);
        cur = new Set([...base].filter((id) => !m.has(id)));
      }
      continue;
    }
    // links: only the kind can be told apart on the canvas
    let kinds: Set<string> | "all" = "all";
    let unresolved = false;
    for (const c of layer.subgraph.edges ?? []) {
      if (c.t === "all") continue;
      if (c.t === "type") {
        const k = linkKindsOf(c.value, presentKinds);
        if (!k) {
          skip(`${label}: links of kind ${c.value} are not drawn apart`);
          unresolved = true;
          continue;
        }
        kinds = new Set([...(kinds === "all" ? [] : kinds), ...k]);
      } else {
        skip(`${label}: link ${c.t} (links are drawn off by kind only)`);
        unresolved = true;
      }
    }
    legend.push({ id: layer.id, group: "links", label });
    // a condition the canvas cannot tell apart must not widen the layer to every link
    if (unresolved && kinds === "all") continue;
    if (layer.kind === "hide") {
      const k = kinds === "all" ? presentKinds : kinds;
      hiddenKinds = new Set([...(hiddenKinds ?? []), ...k]);
      if (shownKinds) for (const x of k) shownKinds.delete(x);
    } else {
      const k = kinds === "all" ? new Set(presentKinds) : kinds;
      const allowed: Set<string> = new Set([...(shownKinds ?? []), ...k]);
      shownKinds = allowed;
      hiddenKinds = new Set([...presentKinds].filter((x) => !allowed.has(x)));
    }
  }
  return { nodeIds: cur, hiddenLinkKinds: hiddenKinds ?? new Set(), patch, skipped, legend };
}

/** Legend rows from a stack alone (no graph needed): its style layers and what it does to links. */
export function legendRows(vs: ViewStack): LegendRow[] {
  return vs.layers
    .filter((l) => !l.legacy && (l.kind === "style" || l.target === "edges"))
    .map((l) => ({ id: l.id, group: l.target === "nodes" ? ("pages" as const) : ("links" as const), label: describe(l) }));
}

// ---- the main parameter a chip edits
export type MainParam =
  | { kind: "hops"; n: number }
  | { kind: "node"; value: string }
  | { kind: "edgeType"; value: string }
  | { kind: "color"; value: string };

export function mainParam(layer: Layer): MainParam | null {
  if (layer.legacy) return null;
  const h = layer.subgraph.nodes?.find((c): c is Extract<NodeCond, { t: "hops" }> => c.t === "hops");
  if (h) return { kind: "hops", n: h.n };
  const nm = layer.subgraph.nodes?.find((c): c is Extract<NodeCond, { t: "name" }> => c.t === "name");
  if (nm) return { kind: "node", value: nm.slugs.join(", ") };
  const et = layer.subgraph.edges?.find((c): c is Extract<EdgeCond, { t: "type" }> => c.t === "type");
  if (et) return { kind: "edgeType", value: et.value };
  if (typeof layer.style?.color === "string") return { kind: "color", value: layer.style.color };
  return null;
}

/** The layer with its main parameter changed; its chip words are written again from the new value. */
export function withParam(layer: Layer, p: MainParam): Layer {
  const next: Layer = { ...layer, text: "", subgraph: { ...layer.subgraph } };
  if (p.kind === "hops") next.subgraph.nodes = (layer.subgraph.nodes ?? []).map((c) => (c.t === "hops" ? { ...c, n: Math.max(1, Math.round(p.n)) } : c));
  else if (p.kind === "node") next.subgraph.nodes = (layer.subgraph.nodes ?? []).map((c) => (c.t === "name" ? { ...c, slugs: p.value.split(",").map((s) => s.trim()).filter(Boolean) } : c));
  else if (p.kind === "edgeType") next.subgraph.edges = (layer.subgraph.edges ?? []).map((c) => (c.t === "type" ? { ...c, value: p.value } : c));
  else next.style = { ...layer.style, color: p.value as ColorBy };
  return next;
}
