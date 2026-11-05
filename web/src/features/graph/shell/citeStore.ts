import { create } from "zustand";

/**
 * The pages the answer on screen in the left chat panel cites (flag `spark-chat`), lit on the graph beside it.
 * A highlight of its own: it never touches the selection, and it ends when the panel closes or the answer is gone.
 */
interface CiteState {
  /** page ids, in the order the answer cites them */
  slugs: readonly string[];
  /** bumped to ask the canvas to frame the cited pages in the area right of the panel */
  fitTick: number;
  /** a click on a lit page asks the panel to scroll to the sentence that cites it */
  scrollReq: { slug: string; tick: number } | null;
  setSlugs: (slugs: readonly string[]) => void;
  refit: () => void;
  scrollTo: (slug: string) => void;
  clear: () => void;
}

const same = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((s, i) => s === b[i]);

export const useCites = create<CiteState>((set, get) => ({
  slugs: [],
  fitTick: 0,
  scrollReq: null,
  setSlugs: (slugs) => {
    if (!same(get().slugs, slugs)) set({ slugs });
  },
  refit: () => set((s) => ({ fitTick: s.fitTick + 1 })),
  scrollTo: (slug) => set((s) => ({ scrollReq: { slug, tick: (s.scrollReq?.tick ?? 0) + 1 } })),
  clear: () => {
    if (get().slugs.length) set({ slugs: [] });
  },
}));
