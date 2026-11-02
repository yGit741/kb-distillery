import { create } from "zustand";
import { useKb } from "@/lib/store";

/** What the bottom drawer shows: one format's table, the files behind the selection, or a paper's citations. */
export type DrawerView =
  | { kind: "format"; format: string; path?: string }
  | { kind: "selection"; path?: string }
  | { kind: "genealogy"; focus: string };

const RAW_KEY = "kb-graph-raw-layer-v1";

function loadRaw(): boolean {
  try {
    return localStorage.getItem(RAW_KEY) === "1";
  } catch {
    return false;
  }
}

interface LayerState {
  /** The data layer (raw piles) is loaded and drawn. Off by default: its payload is large. */
  rawOn: boolean;
  drawer: DrawerView | null;
  /** What each "+ neighbours" step added, newest last, so Collapse can take them back one step at a time. */
  expansions: string[][];
  setRaw: (on: boolean) => void;
  openDrawer: (view: DrawerView | null) => void;
  pushExpansion: (ids: string[]) => void;
  popExpansion: () => string[];
}

export const useLayer = create<LayerState>((set, get) => ({
  rawOn: loadRaw(),
  drawer: null,
  expansions: [],
  setRaw: (on) => {
    try {
      localStorage.setItem(RAW_KEY, on ? "1" : "0");
    } catch {
      /* private mode: the choice just does not persist */
    }
    set({ rawOn: on, ...(on ? {} : { drawer: get().drawer?.kind === "format" ? null : get().drawer }) });
  },
  openDrawer: (drawer) => set({ drawer }),
  pushExpansion: (ids) => set((s) => (ids.length ? { expansions: [...s.expansions, ids] } : s)),
  popExpansion: () => {
    const { expansions } = get();
    const last = expansions[expansions.length - 1] ?? [];
    set({ expansions: expansions.slice(0, -1) });
    return last;
  },
}));

// an emptied selection forgets its expansions: Collapse has nothing left to take back
useKb.subscribe((s, prev) => {
  if (s.selection !== prev.selection && s.selection.size === 0 && useLayer.getState().expansions.length) useLayer.setState({ expansions: [] });
});
