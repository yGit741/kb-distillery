import { create } from "zustand";

/** The uncited clump whose list is open (Citations by meaning), and the paper the list should show. */
export interface RimListState {
  open: { name: string; ids: readonly string[]; set: ReadonlySet<string> } | null;
  focus: string | null;
  show: (name: string, ids: readonly string[], focus?: string | null) => void;
  close: () => void;
}

export const useRimList = create<RimListState>((set) => ({
  open: null,
  focus: null,
  show: (name, ids, focus = null) => set({ open: { name, ids, set: new Set(ids) }, focus }),
  close: () => set({ open: null, focus: null }),
}));
