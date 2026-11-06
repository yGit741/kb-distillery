import { create } from "zustand";
import { useKb } from "@/lib/store";
import { marker, restore, snapshot, type Marker, type Snapshot } from "../shell/shape";
import { useShellStore } from "../shell/shellStore";
import { useGraphUi } from "../store";
import { print } from "./grammar";
import {
  EMPTY_STACK,
  evaluate,
  makeLayer,
  remove as removeLayer,
  replace as replaceLayers,
  stack as stackLayers,
  update as updateLayer,
  type EvalGraph,
  type KnobPatch,
  type Layer,
  type ViewStack,
} from "./model";

/**
 * The view stack on screen (flag graph-intent). Every change pushes the previous stack, with the knobs it was drawn
 * with, on `history`; undo gives both back. Applying folds `evaluate` into the graph's own knobs, the way useShape does
 * for a free-text shape, and remembers a marker so a change by hand retires the stack's "applied" state.
 */

export const HISTORY_MAX = 20;

/** What the screen gives the store: the loaded graph, and how to draw a set of pages. */
export interface GraphContext extends EvalGraph {
  /** Draw exactly these pages (GraphShell `onShowExact`). */
  show: (ids: string[]) => void;
  /** Apply a V1 pinned spec (`applySpec`). */
  applyLegacy?: (spec: Record<string, unknown>) => void;
}

export interface Entry {
  stack: ViewStack;
  snap: Snapshot;
}

export type StackOp = "replace" | "stack" | "remove";

/** A `>` sentence read but not applied yet: what the canvas shows tentatively and the line under the input. */
export interface Preview {
  layers: Layer[];
  op: Exclude<StackOp, "remove">;
  /** The resolved sentence, one line of the language per layer. */
  lines: string[];
  /** Pages that would be drawn. */
  count: number;
  /** The pages that would stay, or null when the layers restrict nothing. */
  ids: ReadonlySet<string> | null;
}

interface LayersState {
  /** A live preview (null = none): the canvas lights `ids`, nothing is hidden and the stack is untouched. */
  preview: Preview | null;
  setPreview: (op: Preview["op"], layers: Layer[]) => boolean;
  /** Apply the previewed layers (one undo step). */
  commitPreview: () => boolean;
  /** Drop the preview and give back the knobs it tinted. */
  cancelPreview: () => void;
  stack: ViewStack;
  /** Undo: the stacks before, newest last, each with the knobs it was drawn with (at most HISTORY_MAX). */
  history: Entry[];
  /** Redo: what undo took back, newest last. */
  future: Entry[];
  graph: GraphContext | null;
  /** The knobs as drawn when the stack was applied; null once a change by hand (or nothing applied). */
  applied: Marker | null;
  /** What the last fold could not evaluate or draw, with the reason. */
  skipped: string[];
  setGraph: (g: GraphContext | null) => void;
  /** `replace` and `stack` take layers; `remove` takes the chip text or id. Returns false when `remove` found nothing. */
  apply: (op: StackOp, payload: Layer[] | string) => boolean;
  /** Change one layer where it stands. */
  edit: (id: string, layer: Layer) => void;
  /** Record a stack change already drawn elsewhere (the `>` shape path), with the knobs from before it. */
  recordDrawn: (op: Exclude<StackOp, "remove">, layers: Layer[], before: Snapshot) => void;
  undo: () => boolean;
  redo: () => boolean;
  /** Drop every layer (one step back, like any change). */
  clear: () => void;
}

/** Knobs the stack owns right now, with the value each had before the stack touched it. */
let owned: { patch: Partial<Record<keyof KnobPatch, unknown>>; kinds: { was: ReadonlySet<string> } | null } = { patch: {}, kinds: null };
let restricting = false;
/** The knobs as they were before a preview tinted them. */
let previewKnobs: ReturnType<typeof snapshot> | null = null;

function untint() {
  if (!previewKnobs) return;
  const { selection: _selection, ...knobs } = previewKnobs;
  useGraphUi.setState(knobs);
  previewKnobs = null;
}

function draw(next: ViewStack, g: GraphContext | null): { skipped: string[] } {
  if (!g) return { skipped: [] };
  const ev = evaluate(next, g);
  const ui = useGraphUi.getState();
  const set: Record<string, unknown> = {};
  // a knob a removed layer styled goes back to what it was before the stack took it
  for (const k of Object.keys(owned.patch) as (keyof KnobPatch)[])
    if (!(k in ev.patch)) {
      set[k] = owned.patch[k];
      delete owned.patch[k];
    }
  for (const k of Object.keys(ev.patch) as (keyof KnobPatch)[]) {
    if (!(k in owned.patch)) owned.patch[k] = ui[k];
    set[k] = ev.patch[k];
  }
  if (ev.patch.colorBy && ev.patch.colorBy !== ui.colorBy) set.hiddenKeys = new Set();
  if (ev.hiddenLinkKinds.size) {
    if (!owned.kinds) owned.kinds = { was: ui.hiddenLinkKinds };
    set.hiddenLinkKinds = ev.hiddenLinkKinds;
  } else if (owned.kinds) {
    set.hiddenLinkKinds = owned.kinds.was;
    owned.kinds = null;
  }
  if (Object.keys(set).length) useGraphUi.setState({ ...set, story: "" });
  const legacy = next.layers.find((l) => l.legacy);
  if (legacy?.legacy) g.applyLegacy?.(legacy.legacy as unknown as Record<string, unknown>);
  else if (ev.nodeIds) g.show([...ev.nodeIds]);
  else if (restricting) {
    useGraphUi.setState({ view: null });
    useKb.getState().clearSelection();
  }
  restricting = ev.nodeIds !== null || !!legacy;
  if (restricting || ev.patch.layoutMode) useGraphUi.getState().fit();
  return { skipped: ev.skipped };
}

export const useLayers = create<LayersState>((set, get) => {
  const commit = (next: ViewStack, before: Snapshot, drawNow: boolean) => {
    const s = get();
    const history = [...s.history, { stack: s.stack, snap: before }].slice(-HISTORY_MAX);
    const { skipped } = drawNow ? draw(next, s.graph) : { skipped: s.skipped };
    set({ stack: next, history, future: [], applied: marker(), skipped });
  };
  return {
    preview: null,
    setPreview: (op, layers) => {
      const s = get();
      if (!s.graph) return false;
      untint();
      const next = (op === "replace" ? replaceLayers : stackLayers)(s.stack, layers);
      const ev = evaluate(next, s.graph);
      // a style layer tints through the same knobs, tentatively
      const tint: Record<string, unknown> = { ...ev.patch };
      if (ev.hiddenLinkKinds.size) tint.hiddenLinkKinds = ev.hiddenLinkKinds;
      if (Object.keys(tint).length) {
        previewKnobs = snapshot();
        useGraphUi.setState(tint);
      }
      set({ preview: { layers, op, lines: layers.map(print), count: ev.nodeIds ? ev.nodeIds.size : s.graph.nodes.length, ids: ev.nodeIds } });
      return true;
    },
    cancelPreview: () => {
      untint();
      if (get().preview) set({ preview: null });
    },
    commitPreview: () => {
      const p = get().preview;
      if (!p) return false;
      untint();
      set({ preview: null });
      return get().apply(p.op, p.layers);
    },
    stack: EMPTY_STACK,
    history: [],
    future: [],
    graph: null,
    applied: null,
    skipped: [],
    setGraph: (graph) => set({ graph }),
    apply: (op, payload) => {
      const s = get();
      let next: ViewStack;
      if (op === "remove") {
        next = removeLayer(s.stack, String(payload));
        if (next === s.stack) return false;
      } else next = (op === "replace" ? replaceLayers : stackLayers)(s.stack, payload as Layer[]);
      commit(next, snapshot(), true);
      return true;
    },
    edit: (id, layer) => commit(updateLayer(get().stack, id, layer), snapshot(), true),
    recordDrawn: (op, layers, before) => {
      const s = get();
      // the shape path drew the pages itself: the store only remembers that they are restricted
      restricting = true;
      commit((op === "replace" ? replaceLayers : stackLayers)(s.stack, layers), before, false);
    },
    undo: () => {
      const s = get();
      const e = s.history.at(-1);
      if (!e) return false;
      const here: Entry = { stack: s.stack, snap: snapshot() };
      restore(e.snap);
      owned = { patch: {}, kinds: null };
      restricting = useGraphUi.getState().view !== null;
      useShellStore.getState().clearShape();
      set({ stack: e.stack, history: s.history.slice(0, -1), future: [...s.future, here], applied: marker() });
      return true;
    },
    redo: () => {
      const s = get();
      const e = s.future.at(-1);
      if (!e) return false;
      const here: Entry = { stack: s.stack, snap: snapshot() };
      restore(e.snap);
      owned = { patch: {}, kinds: null };
      restricting = useGraphUi.getState().view !== null;
      set({ stack: e.stack, future: s.future.slice(0, -1), history: [...s.history, here].slice(-HISTORY_MAX), applied: marker() });
      return true;
    },
    clear: () => {
      if (!get().stack.layers.length) return;
      commit(EMPTY_STACK, snapshot(), true);
    },
  };
});

/** A `show` layer for a sentence the parser does not read yet. */
export const sentenceLayer = (text: string): Layer => makeLayer("show", "nodes", {}, text);

/** Whether the stack is still what is drawn: false once a knob was changed by hand. */
export const stackCurrent = (applied: Marker | null, ui: Marker): boolean => !!applied && (Object.keys(applied) as (keyof Marker)[]).every((k) => applied[k] === ui[k]);
