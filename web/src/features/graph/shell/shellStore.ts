import { create } from "zustand";
import type { PinnedView } from "@/api";
import type { Marker, Snapshot } from "./shape";

/**
 * State of the graph shell (flag graph-shell) that other parts of the screen reach for. The search panel
 * records what the user asked for; free-text shaping acts on it (./useShape) and keeps the shape on screen
 * with its one level of undo here. Opening a pinned view lands in a later PR and reads `pendingView`.
 */
/** The shape on screen: what the status pill says, and the graph state that proves it is still what is drawn. */
export interface AppliedShape {
  text: string;
  /** The canonical style the backend answered (empty when the text was only a selection). */
  styleText: string;
  /** Pages drawn; null when the text was a style only (the pages stayed). */
  pages: number | null;
  /** Clauses the graph cannot draw yet, each with its reason. */
  skipped: string[];
  after: Marker;
}

interface ShellState {
  /** The last free-text shaping request ("colour by area, size by links"); null once handled. */
  pendingShape: string | null;
  /** The last pinned view picked in the search panel; null once handled. */
  pendingView: PinnedView | null;
  /** A shaping request is on its way to the backend. */
  shaping: boolean;
  /** The last shape, shown as a status pill in the panel until it is undone or replaced by hand. */
  shape: AppliedShape | null;
  /** One level of undo: the graph as it was before the last shape. */
  undo: Snapshot | null;
  /** Why the last request did not change the graph; null otherwise. */
  shapeError: string | null;
  /** A quiet one-line notice under the search bar. */
  notice: { id: number; text: string } | null;
  requestShape: (text: string) => void;
  requestView: (view: PinnedView) => void;
  /** Mark a request handled. */
  clearPending: () => void;
  say: (text: string) => void;
  setShaping: (shaping: boolean) => void;
  setShapeError: (error: string | null) => void;
  /** Record a shape that was drawn, with the graph state before it. */
  setShape: (shape: AppliedShape, undo: Snapshot) => void;
  /** Forget the shape and its undo (after undoing). */
  clearShape: () => void;
  dismissNotice: () => void;
}

let noticeId = 0;

export const useShellStore = create<ShellState>((set) => ({
  pendingShape: null,
  pendingView: null,
  notice: null,
  shaping: false,
  shape: null,
  undo: null,
  shapeError: null,
  requestShape: (text) => set({ pendingShape: text }),
  requestView: (view) => set({ pendingView: view }),
  clearPending: () => set({ pendingShape: null, pendingView: null }),
  say: (text) => set({ notice: { id: ++noticeId, text } }),
  setShaping: (shaping) => set({ shaping }),
  setShapeError: (shapeError) => set({ shapeError }),
  setShape: (shape, undo) => set({ shape, undo, shapeError: null }),
  clearShape: () => set({ shape: null, undo: null }),
  dismissNotice: () => set({ notice: null }),
}));

/** The plain `requestShape(text)` of the brief, for callers outside React. */
export const requestShape = (text: string) => useShellStore.getState().requestShape(text);

const SHAPE_WORDS = /\b(group by|colou?r by|size by|layout|hide)\b/i;

/** Whether free text reads as a command to reshape the graph rather than a question or a page search. */
export function looksLikeShape(text: string): boolean {
  const t = text.trim();
  return /^match\b/i.test(t) || SHAPE_WORDS.test(t);
}
