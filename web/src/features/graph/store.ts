import { create } from "zustand";
import type { GraphView } from "./pageSearch";
import { DEFAULT_LAB, sanitizeLab, type LabConfig } from "./lab/config";
import { DEFAULT_STORY, storyById, storyLab, type LayoutMode } from "./lab/views";
import { liveEdgeStory } from "./storyEdges";
import type { Predicate } from "./publicPredicate";
import { QUICK_OFF, type QuickFilters } from "./quickFilters";
import { newRule, type Rule } from "./rules";
import type { ColorBy, SizeBy } from "./style";

/** "filter" | "layout" | "help", or the id of a registered tool (./tools). */
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
  /** Focus a page only once the pointer settles on it, and fade the rest instead of flashing it. */
  calmHover: boolean;
  /** The label rail's settings (./lab). */
  lab: LabConfig;
  /** The view (user story) the settings came from; "" once a knob was changed by hand. */
  story: string;
  layoutMode: LayoutMode;
  /** How strongly pages are pulled toward their theme's anchor in the anchored layout. */
  areaPull: number;
  railOpen: boolean;
  charge: number;
  linkDistance: number;
  gravity: number;
  liveSync: boolean;
}

const ORIENT = storyById(DEFAULT_STORY);

export const DEFAULT_PREFS: GraphPrefs = {
  colorBy: ORIENT?.colorBy ?? "type",
  sizeBy: ORIENT?.sizeBy ?? "tier",
  nodeSize: 5,
  linkOpacity: 0.35,
  arrows: false,
  highlight: true,
  magnet: true,
  calmHover: true,
  lab: ORIENT ? storyLab(ORIENT) : DEFAULT_LAB,
  story: DEFAULT_STORY,
  layoutMode: "anchored",
  areaPull: 0.06,
  railOpen: false,
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
  /** Colour-key rows clicked off in the legend (labels of ./style colorKey for the current colouring). */
  hiddenKeys: ReadonlySet<string>;
  search: string;
  rules: Rule[];
  typeLabels: ReadonlySet<string>;
  /** Types spotlit from the legend (a chip under the pointer): the rest fades, through the hover fade. null = none. */
  spotlight: ReadonlySet<string> | null;
  /** Pages spotlit by id (the Health dial: the concepts a source kind feeds): the rest fades the same way. null = none. */
  spotIds: ReadonlySet<string> | null;
  /** The legend's one-click filters (./quickFilters): Recent, Connected, Backbone, Neighbours, Path. */
  quick: QuickFilters;
  /** The view whose relation kinds are the drawn links (Citations): set by `applyStory`, kept while the legend's
   * filters change (they clear `story`), dropped by another view or Reset. */
  edgeStory: string;
  view: GraphView | null;
  /** Link kinds drawn off (free-text shaping: `hide MENTIONS`). Empty = every kind drawn; the layout is unchanged. */
  hiddenLinkKinds: ReadonlySet<string>;
  /** The story's own page rule (Map draws only public pages); null = none. */
  predicate: Predicate | null;
  /** Sources revealed by "See sources (N)". */
  revealed: ReadonlySet<string>;
  flyout: Flyout | null;
  detailsOpen: boolean;
  readerSlug: string | null;
  /** Pages being read one after another (Read on a set); the reader steps through it. */
  readerSet: string[];
  focusRequest: FocusRequest | null;
  /** Bump to ask the canvas to fit the view. */
  fitTick: number;

  set: (patch: Partial<GraphUiState>) => void;
  /** Chips only add to or take from the set they show; the view's predicate stays until its own chip (or Show all) drops it, so two clicks undo each other. */
  toggleType: (type: string, allTypes: readonly string[], defaults: readonly string[]) => void;
  setLayerTypes: (types: readonly string[], on: boolean, allTypes: readonly string[], defaults: readonly string[]) => void;
  toggleDepth: (depth: string, all: readonly string[]) => void;
  toggleKey: (label: string) => void;
  toggleTypeLabels: (type: string) => void;
  toggleReveal: (ids: readonly string[]) => void;
  addRule: () => void;
  patchRule: (i: number, patch: Partial<Rule>) => void;
  removeRule: (i: number) => void;
  requestFocus: (id: string, zoom?: boolean) => void;
  fit: () => void;
  openFlyout: (f: Flyout | null) => void;
  resetFilters: () => void;
  /** Change label-rail settings by hand: the view becomes "custom". */
  setLab: (patch: Partial<LabConfig>) => void;
  /** Apply a saved view: its label settings, colour and size, layout, drawn types and "Aa" types. */
  applyStory: (id: string) => void;
}

const PREF_KEY = "kb-graph-prefs-v2";

export function loadPrefs(): GraphPrefs {
  try {
    const raw = localStorage.getItem(PREF_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<GraphPrefs>;
    // "orient" became the headline "map" view: carry everyone who had the old default over
    if (parsed.story === "orient") parsed.story = DEFAULT_STORY;
    const out: Record<string, unknown> = { ...DEFAULT_PREFS };
    for (const k of Object.keys(DEFAULT_PREFS) as (keyof GraphPrefs)[]) {
      const v = parsed[k];
      if (k === "lab") out[k] = sanitizeLab(v);
      else if (v !== undefined && typeof v === typeof DEFAULT_PREFS[k]) out[k] = v;
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

/** A saved view brings its drawn types and "Aa" types back on the next visit (they are not stored themselves). */
/** New page types drawn: the view chip goes, and so do a view's own links once its types are no longer all drawn
 *  (hiding every paper type in Citations goes back to page links with nothing still saying Citations). */
function typesPatch(shownTypes: ReadonlySet<string> | null | undefined, edgeStory: string) {
  return { shownTypes, story: "", edgeStory: liveEdgeStory(edgeStory, shownTypes, storyById) ? edgeStory : "" };
}

function initialView(p: GraphPrefs): Pick<GraphUiState, "shownTypes" | "typeLabels" | "predicate"> {
  const st = storyById(p.story);
  return st
    ? { shownTypes: st.types ? new Set(st.types) : undefined, typeLabels: new Set(st.typeLabels ?? []), predicate: st.predicate ?? null }
    : { shownTypes: undefined, typeLabels: new Set(), predicate: null };
}

const INITIAL = loadPrefs();

export const useGraphUi = create<GraphUiState>((set, get) => ({
  ...INITIAL,
  ...initialView(INITIAL),
  edgeStory: storyById(INITIAL.story)?.edges?.length ? INITIAL.story : "",
  shownDepths: null,
  hiddenKeys: new Set(),
  hiddenLinkKinds: new Set(),
  spotlight: null,
  spotIds: null,
  quick: QUICK_OFF,
  search: "",
  rules: [],
  view: null,
  revealed: new Set(),
  flyout: null,
  detailsOpen: false,
  readerSlug: null,
  readerSet: [],
  focusRequest: null,
  fitTick: 0,

  set: (patch) => set(patch),
  toggleType: (type, all, defaults) => {
    const cur = get().shownTypes;
    const base = cur === undefined ? new Set(defaults) : new Set(cur ?? all);
    if (!base.delete(type)) base.add(type);
    set(typesPatch(normalize(base, all), get().edgeStory));
  },
  setLayerTypes: (types, on, all, defaults) => {
    const cur = get().shownTypes;
    const base = cur === undefined ? new Set(defaults) : new Set(cur ?? all);
    for (const t of types) {
      if (on) base.add(t);
      else base.delete(t);
    }
    set(typesPatch(normalize(base, all), get().edgeStory));
  },
  toggleDepth: (depth, all) => {
    const base = new Set(get().shownDepths ?? all);
    if (!base.delete(depth)) base.add(depth);
    set({ shownDepths: all.every((d) => base.has(d)) ? null : base, story: "" });
  },
  toggleKey: (label) => {
    const next = new Set(get().hiddenKeys);
    if (!next.delete(label)) next.add(label);
    set({ hiddenKeys: next, story: "" });
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
  resetFilters: () => set({ shownTypes: undefined, shownDepths: null, search: "", rules: [], view: null, revealed: new Set(), predicate: null, story: "", edgeStory: "", hiddenLinkKinds: new Set() }),
  setLab: (patch) => set((s) => ({ lab: { ...s.lab, ...patch }, story: "" })),
  applyStory: (id) => {
    const st = storyById(id);
    if (!st) return set({ story: "", edgeStory: "" });
    set({
      story: st.id,
      edgeStory: st.edges?.length ? st.id : "",
      lab: storyLab(st),
      colorBy: st.colorBy,
      sizeBy: st.sizeBy,
      layoutMode: st.layoutMode,
      shownTypes: st.types ? new Set(st.types) : undefined,
      typeLabels: new Set(st.typeLabels ?? []),
      predicate: st.predicate ?? null,
      // a story is a whole view: a search, picked pages, a scope or a colour-key filter from before would fight it
      view: null,
      hiddenKeys: new Set(),
      hiddenLinkKinds: new Set(),
      quick: { ...QUICK_OFF, ...st.quick },
      revealed: new Set(),
    });
  },
}));

useGraphUi.subscribe((s, prev) => {
  const a = pickPrefs(s);
  const b = pickPrefs(prev);
  if (PREF_KEYS.some((k) => a[k] !== b[k])) savePrefs(a);
});
