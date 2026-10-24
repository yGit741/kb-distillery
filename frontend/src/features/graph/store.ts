import { create } from "zustand";
import type { GraphView } from "./pageSearch";
import type { LabelField, LabelMode } from "./labels";
import { newRule, type Rule } from "./rules";
import type { ColorBy, SizeBy } from "./style";

/** "filter" | "look" | "layout" | "help", or the id of a registered tool (./tools). */
export type Flyout = string;

/** Settings worth keeping between visits; everything else is the state of this view. */
export interface GraphPrefs {
  colorBy: ColorBy;
  sizeBy: SizeBy;
  nodeSize: number;
  linkOpacity: number;
  arrows: boolean;
  highlight: boolean;
  magnet: boolean;
  labelMode: LabelMode;
  labelField: LabelField;
  charge: number;
  linkDistance: number;
  gravity: number;
  liveSync: boolean;
}

export const DEFAULT_PREFS: GraphPrefs = {
  colorBy: "type",
  sizeBy: "connections",
  nodeSize: 5,
  linkOpacity: 0.35,
  arrows: false,
  highlight: true,
  magnet: true,
  labelMode: "auto",
  labelField: "title",
  charge: -120,
  linkDistance: 70,
  gravity: 0.3,
  liveSync: true,
};

export interface FocusRequest {
  id: string;
  zoom: boolean;
}

export interface GraphUiState extends GraphPrefs {
  /** Types drawn at all. undefined = the schema's default (concepts, people off); null = every type. */
  shownTypes: ReadonlySet<string> | null | undefined;
  shownDepths: ReadonlySet<string> | null;
  search: string;
  rules: Rule[];
  typeLabels: ReadonlySet<string>;
  view: GraphView | null;
  /** Sources revealed by "See sources (N)". */
  revealed: ReadonlySet<string>;
  flyout: Flyout | null;
  detailsOpen: boolean;
  readerSlug: string | null;
  focusRequest: FocusRequest | null;
  /** Bump to ask the canvas to fit the view. */
  fitTick: number;

  set: (patch: Partial<GraphUiState>) => void;
  toggleType: (type: string, allTypes: readonly string[], defaults: readonly string[]) => void;
  setLayerTypes: (types: readonly string[], on: boolean, allTypes: readonly string[], defaults: readonly string[]) => void;
  toggleDepth: (depth: string, all: readonly string[]) => void;
  toggleTypeLabels: (type: string) => void;
  toggleReveal: (ids: readonly string[]) => void;
  addRule: () => void;
  patchRule: (i: number, patch: Partial<Rule>) => void;
  removeRule: (i: number) => void;
  requestFocus: (id: string, zoom?: boolean) => void;
  fit: () => void;
  openFlyout: (f: Flyout | null) => void;
  resetFilters: () => void;
}

const PREF_KEY = "kb-graph-prefs-v1";

export function loadPrefs(): GraphPrefs {
  try {
    const raw = localStorage.getItem(PREF_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<GraphPrefs>;
    const out: Record<string, unknown> = { ...DEFAULT_PREFS };
    for (const k of Object.keys(DEFAULT_PREFS) as (keyof GraphPrefs)[]) {
      const v = parsed[k];
      if (v !== undefined && typeof v === typeof DEFAULT_PREFS[k]) out[k] = v;
    }
    return out as unknown as GraphPrefs;
  } catch {
    return DEFAULT_PREFS;
  }
}

export function savePrefs(s: GraphPrefs): void {
  try {
    localStorage.setItem(PREF_KEY, JSON.stringify(s));
  } catch {
    /* private mode: the settings just do not persist */
  }
}

const PREF_KEYS = Object.keys(DEFAULT_PREFS) as (keyof GraphPrefs)[];
const pickPrefs = (s: GraphPrefs): GraphPrefs => Object.fromEntries(PREF_KEYS.map((k) => [k, s[k]])) as unknown as GraphPrefs;

/** Normalise "every type on" to null so the Concepts/All shortcuts and the chips agree. */
const normalize = (next: Set<string>, all: readonly string[]) => (all.every((t) => next.has(t)) ? null : next);

export const useGraphUi = create<GraphUiState>((set, get) => ({
  ...loadPrefs(),
  shownTypes: undefined,
  shownDepths: null,
  search: "",
  rules: [],
  typeLabels: new Set(),
  view: null,
  revealed: new Set(),
  flyout: null,
  detailsOpen: false,
  readerSlug: null,
  focusRequest: null,
  fitTick: 0,

  set: (patch) => set(patch),
  toggleType: (type, all, defaults) => {
    const cur = get().shownTypes;
    const base = cur === undefined ? new Set(defaults) : new Set(cur ?? all);
    if (!base.delete(type)) base.add(type);
    set({ shownTypes: normalize(base, all) });
  },
  setLayerTypes: (types, on, all, defaults) => {
    const cur = get().shownTypes;
    const base = cur === undefined ? new Set(defaults) : new Set(cur ?? all);
    for (const t of types) {
      if (on) base.add(t);
      else base.delete(t);
    }
    set({ shownTypes: normalize(base, all) });
  },
  toggleDepth: (depth, all) => {
    const base = new Set(get().shownDepths ?? all);
    if (!base.delete(depth)) base.add(depth);
    set({ shownDepths: all.every((d) => base.has(d)) ? null : base });
  },
  toggleTypeLabels: (type) => {
    const next = new Set(get().typeLabels);
    if (!next.delete(type)) next.add(type);
    set({ typeLabels: next });
  },
  toggleReveal: (ids) => {
    const cur = get().revealed;
    const all = ids.length > 0 && ids.every((i) => cur.has(i));
    const next = new Set(cur);
    for (const i of ids) {
      if (all) next.delete(i);
      else next.add(i);
    }
    set({ revealed: next });
  },
  addRule: () => set((s) => ({ rules: [...s.rules, newRule()] })),
  patchRule: (i, patch) => set((s) => ({ rules: s.rules.map((r, j) => (j === i ? { ...r, ...patch } : r)) })),
  removeRule: (i) => set((s) => ({ rules: s.rules.filter((_, j) => j !== i) })),
  requestFocus: (id, zoom = true) => set({ focusRequest: { id, zoom } }),
  fit: () => set((s) => ({ fitTick: s.fitTick + 1 })),
  openFlyout: (f) => set((s) => ({ flyout: s.flyout === f ? null : f })),
  resetFilters: () => set({ shownTypes: undefined, shownDepths: null, search: "", rules: [], view: null, revealed: new Set() }),
}));

useGraphUi.subscribe((s, prev) => {
  const a = pickPrefs(s);
  const b = pickPrefs(prev);
  if (PREF_KEYS.some((k) => a[k] !== b[k])) savePrefs(a);
});
