import { create } from "zustand";

/** Page ids and the applied view's query lines, written as a plain footer under a quick thought. */
export interface CaptureContext {
  ids: string[];
  view: string[];
}

/** Page ids named in the footer; a capture is capped at 10k characters. */
const FOOTER_IDS = 20;

/** The footer a captured thought carries: the page ids, then the view's lines. Plain text, no markup. */
export function captureFooter(c: CaptureContext | null): string {
  if (!c) return "";
  return [c.ids.length ? `nodes: ${c.ids.slice(0, FOOTER_IDS).join(", ")}${c.ids.length > FOOTER_IDS ? ` and ${c.ids.length - FOOTER_IDS} more` : ""}` : "", c.view.length ? `view: ${c.view.join(" · ")}` : ""].filter(Boolean).join("\n");
}

interface UiState {
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  /** Quick-capture dialog (think inbox), reachable from any screen via ⌘K or ⌘⇧Space. */
  captureOpen: boolean;
  setCaptureOpen: (open: boolean) => void;
  /** What the dialog carries along when opened from the graph menu (flag graph-intent): page ids and the view's query lines. */
  captureContext: CaptureContext | null;
  openCapture: (context: CaptureContext) => void;
  /** The search line as an overlay on screens other than the graph (flag graph-intent), opened by Cmd/Ctrl+K. */
  lineOpen: boolean;
  setLineOpen: (open: boolean) => void;
  /** Cmd-J quick ask (flag `agent-mode`). */
  askOpen: boolean;
  setAskOpen: (open: boolean) => void;
}

export const useUi = create<UiState>((set) => ({
  paletteOpen: false,
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
  captureOpen: false,
  setCaptureOpen: (captureOpen) => set({ captureOpen, captureContext: null }),
  captureContext: null,
  openCapture: (captureContext) => set({ captureOpen: true, captureContext }),
  lineOpen: false,
  setLineOpen: (lineOpen) => set({ lineOpen }),
  askOpen: false,
  setAskOpen: (askOpen) => set({ askOpen }),
}));
