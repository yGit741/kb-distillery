import { create } from "zustand";
import { useFlag } from "@/flags/useFlag";

/** Where this browser keeps the choice ("1" folded, "0" open). */
export const HEADER_FOLD_KEY = "kb-header-folded";

/** The last choice in this browser, folded unless the bar was left open. Storage can throw (private window): never fatal. */
export function readFolded(): boolean {
  try {
    const v = localStorage.getItem(HEADER_FOLD_KEY);
    if (v === "0") return false;
    if (v === "1") return true;
  } catch {
    /* ignore */
  }
  return true;
}

interface HeaderFoldState {
  folded: boolean;
  /** True while the graph's chevron is on screen: the bar only folds when there is a way to bring it back. */
  mounted: boolean;
  setMounted: (mounted: boolean) => void;
  set: (folded: boolean) => void;
  toggle: () => void;
}

/** Flag `header-fold`: whether the app bar is folded away above the graph. The choice is remembered per browser. */
export const useHeaderFold = create<HeaderFoldState>((set, get) => ({
  folded: readFolded(),
  mounted: false,
  setMounted: (mounted) => set({ mounted }),
  set: (folded) => {
    try {
      localStorage.setItem(HEADER_FOLD_KEY, folded ? "1" : "0");
    } catch {
      /* ignore */
    }
    set({ folded });
  },
  toggle: () => get().set(!get().folded),
}));

/**
 * True while the app bar is folded away: flag `header-fold` on, the calm shell on, the graph's chevron mounted
 * (so a loading, error or empty screen, an embed or any other route keeps its bar), and the person's last choice
 * (folded by default). The bar and the graph frame both read this one value, so they never get out of step.
 */
export function useHeaderFolded(): boolean {
  const on = useFlag("header-fold");
  const shell = useFlag("graph-shell");
  const mounted = useHeaderFold((s) => s.mounted);
  const folded = useHeaderFold((s) => s.folded);
  return on && shell && mounted && folded;
}
