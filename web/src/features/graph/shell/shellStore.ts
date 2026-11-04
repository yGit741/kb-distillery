import { create } from "zustand";
import type { PinnedView } from "@/api";

/**
 * State of the graph shell (flag graph-shell) that other parts of the screen reach for. The search panel
 * only records what the user asked for; the pieces that act on it (free-text shaping, opening a pinned view)
 * land in later PRs and read it from here.
 */
interface ShellState {
  /** The last free-text shaping request ("colour by area, size by links"); null once handled. */
  pendingShape: string | null;
  /** The last pinned view picked in the search panel; null once handled. */
  pendingView: PinnedView | null;
  /** A quiet one-line notice under the search bar. */
  notice: { id: number; text: string } | null;
  requestShape: (text: string) => void;
  requestView: (view: PinnedView) => void;
  /** Mark a request handled. */
  clearPending: () => void;
  say: (text: string) => void;
  dismissNotice: () => void;
}

let noticeId = 0;

export const useShellStore = create<ShellState>((set) => ({
  pendingShape: null,
  pendingView: null,
  notice: null,
  requestShape: (text) => set({ pendingShape: text }),
  requestView: (view) => set({ pendingView: view }),
  clearPending: () => set({ pendingShape: null, pendingView: null }),
  say: (text) => set({ notice: { id: ++noticeId, text } }),
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
