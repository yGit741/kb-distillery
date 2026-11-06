import { create } from "zustand";
import type { PinnedView } from "@/api";
import type { Marker, Snapshot } from "./shape";
import type { LineMode } from "./copy";

export type ViewOp = "replace" | "stack" | "remove";

/**
 * State of the graph shell (flag graph-shell) that other parts of the screen reach for. The search panel
 * records what the user asked for; free-text shaping acts on it (./useShape) and keeps the shape on screen
 * with its one level of undo here. A pinned view picked in the search panel waits in `pendingView` until the corner controls open it.
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
  /** How the last `>` sentence should combine with the current view (flag graph-intent); the layer engine reads it later. */
  pendingOp: ViewOp | null;
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
  setPendingOp: (op: ViewOp | null) => void;
  requestView: (view: PinnedView) => void;
  /** Mark a request handled. */
  clearPending: () => void;
  /** Mark only the pinned-view request handled (a shape request may still be waiting). */
  clearPendingView: () => void;
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
  pendingOp: null,
  notice: null,
  shaping: false,
  shape: null,
  undo: null,
  shapeError: null,
  requestShape: (text) => set({ pendingShape: text }),
  setPendingOp: (pendingOp) => set({ pendingOp }),
  requestView: (view) => set({ pendingView: view }),
  clearPending: () => set({ pendingShape: null, pendingView: null }),
  clearPendingView: () => set({ pendingView: null }),
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

/** The mode a line of text is in: `>` changes the view (`>+` stacks, `>-` removes), `/` runs a command, anything else searches. */
export function parseMode(raw: string): { mode: LineMode; op?: ViewOp; text: string } {
  if (raw.startsWith(">+")) return { mode: "view", op: "stack", text: raw.slice(2).trim() };
  if (raw.startsWith(">-")) return { mode: "view", op: "remove", text: raw.slice(2).trim() };
  if (raw.startsWith(">")) return { mode: "view", op: "replace", text: raw.slice(1).trim() };
  if (raw.startsWith("/")) return { mode: "command", text: raw.slice(1).trim() };
  return { mode: "search", text: raw.trim() };
}
