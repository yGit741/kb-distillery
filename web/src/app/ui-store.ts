import { create } from "zustand";

interface UiState {
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  /** Quick-capture dialog (think inbox), reachable from any screen via ⌘K or ⌘⇧Space. */
  captureOpen: boolean;
  setCaptureOpen: (open: boolean) => void;
  /** Cmd-J quick ask (flag `agent-mode`). */
  askOpen: boolean;
  setAskOpen: (open: boolean) => void;
}

export const useUi = create<UiState>((set) => ({
  paletteOpen: false,
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
  captureOpen: false,
  setCaptureOpen: (captureOpen) => set({ captureOpen }),
  askOpen: false,
  setAskOpen: (askOpen) => set({ askOpen }),
}));
