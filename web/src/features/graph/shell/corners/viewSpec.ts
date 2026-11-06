import { flag } from "@/flags";
import { storyById, storyKnown } from "../../lab/views";
import { describe, fromViewSpecV1, type Layer, type ViewStack } from "../../layers/model";
import { applyLayers, specLayers } from "../../layers/readyViews";
import { useLayers } from "../../layers/store";
import type { QuickFilters } from "../../quickFilters";
import { useGraphUi } from "../../store";
import type { ColorBy, SizeBy } from "../../style";

/**
 * What a pinned view stores (`POST /api/views` spec; the server keeps it opaque). Sets become arrays. `story` is the
 * named view (Map, Thesis, ...) the state came from, or "" once a knob was changed by hand.
 */
export interface ViewSpecV1 {
  v: 1;
  story: string;
  colorBy: ColorBy;
  sizeBy: SizeBy;
  /** "default" = the schema's own, "all" = every type, else the types drawn */
  types: "default" | "all" | string[];
  depths: string[] | null;
  hiddenKeys: string[];
  quick: QuickFilters;
  /** the pages of a picked / search / scope view, when one is on */
  pages?: string[];
}

/** What a pinned view stores with flag graph-intent: the layer stack as it is, and its plain words. */
export interface ViewSpecV2 {
  v: 2;
  layers: Layer[];
  text: string;
}

type Ui = ReturnType<typeof useGraphUi.getState>;
type CaptureUi = Pick<Ui, "story" | "colorBy" | "sizeBy" | "shownTypes" | "shownDepths" | "hiddenKeys" | "quick" | "view">;

/**
 * The spec to pin. With a layer stack that has layers (flag graph-intent) it is the stack, `{ v: 2, layers, text }`;
 * otherwise the knobs as before (V1), so a view set by hand still pins.
 */
export function captureSpec(ui: CaptureUi): ViewSpecV1;
export function captureSpec(ui: CaptureUi, stack: ViewStack | undefined): ViewSpecV1 | ViewSpecV2;
export function captureSpec(ui: CaptureUi, stack?: ViewStack): ViewSpecV1 | ViewSpecV2 {
  if (stack?.layers.length) return { v: 2, layers: stack.layers, text: stack.layers.map(describe).join(" · ") };
  const pages = ui.view ? [...ui.view.hits].slice(0, 2000) : [];
  return {
    v: 1,
    story: ui.story,
    colorBy: ui.colorBy,
    sizeBy: ui.sizeBy,
    types: ui.shownTypes === undefined ? "default" : ui.shownTypes === null ? "all" : [...ui.shownTypes].sort(),
    depths: ui.shownDepths ? [...ui.shownDepths].sort() : null,
    hiddenKeys: [...ui.hiddenKeys].sort(),
    quick: ui.quick,
    ...(pages.length ? { pages } : {}),
  };
}

export interface ApplyDeps {
  /** the screen's own path for a named view (its seed, URL and fit) */
  applyView: (id: string) => void;
  showPicked: (ids: string[]) => void;
}

const isArr = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === "string");

/**
 * Apply a stored spec: the named view first (it resets the knobs it owns), then the rest on top. Missing keys are
 * left alone, so a spec written by another part of the app applies as far as it is understood.
 * Returns false when nothing in it was recognised (the row then says so instead of doing nothing silently).
 */
export function applySpec(spec: Record<string, unknown>, deps: ApplyDeps, pin?: { name: string }): boolean {
  // flag graph-intent: a pinned view is a layer stack. A v2 spec applies as layers (replacing the view); a V1 spec as one
  // "legacy" layer named like the pin, drawn by `applySpecV1` through the layer store.
  if (flag("graph-intent")) {
    const layers = specLayers(spec);
    if (layers) return applyLayers("replace", layers);
    if (pin && spec.v !== 2 && recognisedV1(spec) && useLayers.getState().graph) return applyLayers("replace", fromViewSpecV1(spec as unknown as ViewSpecV1, pin.name).layers);
  }
  return applySpecV1(spec, deps);
}

const V1_KEYS = ["story", "types", "depths", "colorBy", "sizeBy", "hiddenKeys", "quick", "pages"];
/** Whether a spec holds anything the V1 restore understands. */
export const recognisedV1 = (spec: Record<string, unknown>): boolean => V1_KEYS.some((k) => k in spec);

/** Apply a V1 spec to the knobs and pages directly (no layer stack). */
export function applySpecV1(spec: Record<string, unknown>, deps: ApplyDeps): boolean {
  let did = false;
  const story = typeof spec.story === "string" && spec.story && storyKnown(spec.story) ? spec.story : "";
  if (story) {
    deps.applyView(story);
    did = true;
  }
  const patch: Partial<Ui> = {};
  if (spec.types === "default") patch.shownTypes = undefined;
  else if (spec.types === "all") patch.shownTypes = null;
  else if (isArr(spec.types)) patch.shownTypes = new Set(spec.types);
  if (spec.depths === null) patch.shownDepths = null;
  else if (isArr(spec.depths)) patch.shownDepths = new Set(spec.depths);
  if (typeof spec.colorBy === "string") patch.colorBy = spec.colorBy as ColorBy;
  if (typeof spec.sizeBy === "string") patch.sizeBy = spec.sizeBy as SizeBy;
  if (isArr(spec.hiddenKeys)) patch.hiddenKeys = new Set(spec.hiddenKeys);
  if (spec.quick && typeof spec.quick === "object") patch.quick = { ...useGraphUi.getState().quick, ...(spec.quick as Partial<QuickFilters>) };
  if (Object.keys(patch).length) {
    // a spec with no named view stands on its own: the story marker clears, as for any change by hand
    useGraphUi.setState({ ...patch, story: typeof spec.story === "string" ? story || "" : useGraphUi.getState().story });
    did = true;
  }
  // a restore replaces the pages on screen (never unions with them); a named view brings its own pages
  if (!story && (did || (isArr(spec.pages) && spec.pages.length))) useGraphUi.setState({ view: null });
  if (!story && isArr(spec.pages) && spec.pages.length) {
    deps.showPicked(spec.pages);
    did = true;
  }
  return did;
}

/** A default name for the view about to be pinned. */
export function suggestName(ui: Pick<Ui, "story" | "view">): string {
  const st = ui.story ? storyById(ui.story) : undefined;
  if (st) return st.headline?.label ?? st.name.split(":")[0]!;
  if (ui.view) return ui.view.label || "Picked pages";
  return "Untitled view";
}
