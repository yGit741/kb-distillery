import { create } from "zustand";
import { flag } from "@/flags";
import { IS_SHARE } from "@/share/env";

/**
 * State of the left chat panel (flag `spark-chat`). `key` changes each time a chat is opened, so the panel remounts
 * and reads the freshly stored chat (the same trick the right dock uses).
 */
interface SparkPanelState {
  open: boolean;
  key: number;
  show: () => void;
  close: () => void;
}

export const useSparkPanel = create<SparkPanelState>((set) => ({
  open: false,
  key: 0,
  show: () => set((s) => ({ open: true, key: s.key + 1 })),
  close: () => set({ open: false }),
}));

/**
 * Whether a chat opens in the left panel rather than the right dock: flag `spark-chat` with the calm shell (the
 * panel lives in the shell frame) and never in a share build (no chat code there). Every opener asks this one rule.
 */
export function chatInPanel(): boolean {
  return flag("spark-chat") && flag("graph-shell") && !IS_SHARE && import.meta.env.MODE !== "share";
}
