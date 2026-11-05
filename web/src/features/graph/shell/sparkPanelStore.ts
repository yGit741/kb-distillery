import { create } from "zustand";

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
