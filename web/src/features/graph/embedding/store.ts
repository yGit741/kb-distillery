import { create } from "zustand";
import { flag } from "@/flags";
import { useGraphUi } from "../store";
import type { Pair } from "./model";
import { EMBED_VIEWS, type EmbedView } from "./model";

/**
 * The embedding view on screen (flag ui.embedding-views) and what the canvas reads to draw it. Not kept between
 * visits: a pinned view brings it back.
 */
export interface EmbedState {
  view: EmbedView | null;
  /** the meaning map's components, x then y */
  axes: readonly [number, number];
  /** the missing-links list's tab */
  tab: "pairs" | "orphans";
  /** each page's 0..1 position along the components, once the embedding is loaded */
  pc: ReadonlyMap<string, readonly number[]> | null;
  /** the missing-links lens: the candidate pairs and their pages (the rest is drawn grey) */
  lens: { pairs: readonly Pair[]; pages: ReadonlySet<string> } | null;
  set: (patch: Partial<Omit<EmbedState, "set">>) => void;
}

export const useEmbedView = create<EmbedState>((set) => ({
  view: null,
  axes: [0, 1],
  tab: "pairs",
  pc: null,
  lens: null,
  set: (patch) => set(patch),
}));

/** What a pinned embedding view stores: `{ v: 1, story: "", embed: { view, axes? } }`. */
export type EmbedSpec = {
  v: 1;
  story: "";
  embed: { view: EmbedView; axes?: [number, number] };
};

export function embedSpec(view: EmbedView, axes: readonly [number, number] = [0, 1]): EmbedSpec {
  return { v: 1, story: "", embed: view === "map" ? { view, axes: [axes[0], axes[1]] } : { view } };
}

/** The embedding view a spec names, or null. */
export function embedOf(spec: Record<string, unknown>): EmbedSpec["embed"] | null {
  const e = spec.embed as { view?: unknown; axes?: unknown } | undefined;
  if (!e || typeof e !== "object" || !EMBED_VIEWS.includes(e.view as EmbedView)) return null;
  const ax = Array.isArray(e.axes) && e.axes.length === 2 && e.axes.every((a) => Number.isInteger(a) && a >= 0) ? (e.axes as [number, number]) : undefined;
  return ax ? { view: e.view as EmbedView, axes: ax } : { view: e.view as EmbedView };
}

/** Whether two specs are the same embedding view (a suggestion hides while a pin like it exists). */
export function sameEmbed(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const x = embedOf(a);
  const y = embedOf(b);
  if (!x || !y || x.view !== y.view) return false;
  if (x.view !== "map") return true;
  const ax = x.axes ?? [0, 1];
  const ay = y.axes ?? [0, 1];
  return ax[0] === ay[0] && ax[1] === ay[1];
}

/** The spec of the embedding view on screen, or null when none is. */
export function captureEmbed(): EmbedSpec | null {
  const s = useEmbedView.getState();
  return s.view ? embedSpec(s.view, s.axes) : null;
}

/** The three suggestions the pinned list offers, in order. */
export const SUGGESTED: readonly { view: EmbedView; name: string; hint: string }[] = [
  { view: "topics", name: "Topics", hint: "Colour concepts by the topic their meaning falls in" },
  { view: "map", name: "Meaning map", hint: "Place pages by two directions of meaning" },
  { view: "missing", name: "Missing links", hint: "Pages close in meaning that are not linked" },
];

/**
 * Show an embedding view: Topics and the meaning map colour by topic; missing links keeps the colouring (its lens
 * greys the rest). False with the flag off, so such a pin says it cannot be restored.
 */
export function applyEmbed(e: EmbedSpec["embed"]): boolean {
  if (!flag("ui.embedding-views")) return false;
  const s = useEmbedView.getState();
  s.set({ view: e.view, axes: e.view === "map" ? (e.axes ?? [0, 1]) : s.axes, tab: "pairs" });
  if (e.view !== "missing") useGraphUi.setState({ colorBy: "topic", story: "" });
  else useGraphUi.setState({ story: "" });
  return true;
}

/** Leave the embedding view on screen; `recolour` also drops a topic colouring (back to theme). */
export function leaveEmbed(recolour = true): void {
  useEmbedView.getState().set({ view: null, lens: null });
  if (recolour && useGraphUi.getState().colorBy === "topic") useGraphUi.setState({ colorBy: "area" });
}
