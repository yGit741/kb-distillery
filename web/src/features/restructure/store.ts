import { create } from "zustand";
import type { RestructureKind } from "./lib";

type Open = { kind: RestructureKind; mentions: string[] } | null;

/** Which restructure dialog is open on the page being read; both entry variants (menu, chat commands) call `show`. */
export const useRestructureStore = create<{ open: Open; show: (kind: RestructureKind, mentions?: string[]) => void; close: () => void }>((set) => ({
  open: null,
  show: (kind, mentions = []) => set({ open: { kind, mentions } }),
  close: () => set({ open: null }),
}));
