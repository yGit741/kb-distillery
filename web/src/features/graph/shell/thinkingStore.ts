import { create } from "zustand";
import type { GNode } from "../types";
import type { Role, WebSource } from "./thinking";

/**
 * What "Show my thinking" puts on the graph (flag `show-thinking`): the answer on screen's pages by role, its
 * citation numbers and the web sources it opened. Nothing here moves the camera. `hot` is a citation the reader
 * points at in the answer (its node gets a ring). The marks (missed, bad citation) stay in ./replayStore, whose
 * chips the composer already carries to the next message.
 */
export interface ThinkingGraph {
  /** the message in the chat */
  msg: number;
  roles: Map<string, Role>;
  citeNo: Map<string, number>;
  web: WebSource[];
}

interface ThinkingState {
  view: ThinkingGraph | null;
  /** the message whose graph view the reader dismissed (until the next answer) */
  dismissed: number | null;
  hot: string | null;
  /** the graph's pages (titles and types for the chips), published by the canvas */
  byId: ReadonlyMap<string, GNode> | null;
  set: (view: ThinkingGraph | null) => void;
  dismiss: () => void;
  undismiss: () => void;
  setHot: (slug: string | null) => void;
  clear: () => void;
}

export const useThinking = create<ThinkingState>((set, get) => ({
  view: null,
  dismissed: null,
  hot: null,
  byId: null,
  set: (view) => {
    if (get().view !== view) set({ view });
  },
  dismiss: () => set((s) => ({ dismissed: s.view?.msg ?? null, view: null, hot: null })),
  undismiss: () => set({ dismissed: null }),
  setHot: (hot) => {
    if (get().hot !== hot) set({ hot });
  },
  clear: () => set({ view: null, hot: null, dismissed: null }),
}));
