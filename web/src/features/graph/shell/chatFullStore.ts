import { create } from "zustand";
import { flag } from "@/flags";
import { readJson, writeJson } from "@/features/chat/storage";

/**
 * Size of the one chat surface (flag `chat-full`): `panel` is the left panel beside the graph, `full` the three
 * columns (chat list, chat, graph with a mini explorer). Whether the list shows and whether the right pane is
 * folded to a rail are remembered per browser; the size itself is not (a reload opens the panel).
 */
export const BUSY_NOTICE = "An answer is still on its way. Stop it first, then switch chats.";
const LIST_KEY = "kbchat.full.list";
const FOLD_KEY = "kbchat.full.folded";
const WIDTH_KEY = "kbchat.panel.width";
const EXPLORER_KEY = "kbchat.full.explorer";
const PANE_KEY = "kbchat.full.pane";
/** The panel's width bounds when dragged by its edge. */
export const PANEL_MIN_W = 320;
export const PANEL_MAX_W = 760;
const clampW = (w: number) => Math.round(Math.min(PANEL_MAX_W, Math.max(PANEL_MIN_W, w)));

interface ChatFullState {
  full: boolean;
  listOpen: boolean;
  folded: boolean;
  setFull: (full: boolean) => void;
  toggleList: () => void;
  setFolded: (folded: boolean) => void;
  /** Width of the panel size, dragged by its right edge (remembered per browser). */
  panelW: number;
  setPanelW: (w: number) => void;
  /** Width of the right pane (graph and page viewer) in the full chat, dragged by its edge; null is the default share. */
  paneW: number | null;
  setPaneW: (w: number | null) => void;
  explorerOpen: boolean;
  setExplorerOpen: (open: boolean) => void;
  /** Page ids of the graph, so the composer's @ can complete them (set by the graph screen). */
  pages: readonly { id: string; title: string }[];
  setPages: (pages: readonly { id: string; title: string }[]) => void;
  /** Slugs the last answer cited, newest answer only (the mini explorer lists them). */
  cited: readonly string[];
  setCited: (cited: readonly string[]) => void;
  /** An answer is streaming in the chat panel: nothing may remount it (a remount aborts the stream). */
  busy: boolean;
  setBusy: (busy: boolean) => void;
  /** A quiet line under the chat header ("that chat was not found"); the panel clears it after a while. */
  notice: string;
  setNotice: (notice: string) => void;
  /** Text handed to the composer without remounting it (a question from /chat?q=): `n` makes the same text insert twice. */
  insert: { text: string; n: number } | null;
  insertText: (text: string) => void;
  /** A page the graph handed to the composer (a click on a node): `n` makes the same page insert twice. */
  mention: { id: string; title: string; n: number } | null;
  mentionPage: (id: string, title: string) => void;
}

export const useChatFull = create<ChatFullState>((set, get) => ({
  full: false,
  listOpen: readJson("local", LIST_KEY, true),
  folded: readJson("local", FOLD_KEY, false),
  // growing to full always shows the right pane and its page viewer
  setFull: (full) => {
    if (full) {
      writeJson("local", FOLD_KEY, false);
      writeJson("local", EXPLORER_KEY, true);
      set({ full, folded: false, explorerOpen: true });
    } else set({ full });
  },
  panelW: clampW(readJson("local", WIDTH_KEY, 400)),
  setPanelW: (w) => {
    const panelW = clampW(w);
    writeJson("local", WIDTH_KEY, panelW);
    set({ panelW });
  },
  paneW: readJson<number | null>("local", PANE_KEY, null),
  setPaneW: (paneW) => {
    writeJson("local", PANE_KEY, paneW);
    set({ paneW });
  },
  explorerOpen: readJson("local", EXPLORER_KEY, true),
  setExplorerOpen: (explorerOpen) => {
    writeJson("local", EXPLORER_KEY, explorerOpen);
    set({ explorerOpen });
  },
  toggleList: () => {
    const listOpen = !get().listOpen;
    writeJson("local", LIST_KEY, listOpen);
    set({ listOpen });
  },
  setFolded: (folded) => {
    writeJson("local", FOLD_KEY, folded);
    set({ folded });
  },
  pages: [],
  setPages: (pages) => set({ pages }),
  cited: [],
  setCited: (cited) => set((s) => (s.cited.length === cited.length && s.cited.every((c, i) => c === cited[i]) ? s : { cited })),
  busy: false,
  setBusy: (busy) => set({ busy }),
  notice: "",
  setNotice: (notice) => set({ notice }),
  insert: null,
  insertText: (text) => set((s) => ({ insert: { text, n: (s.insert?.n ?? 0) + 1 } })),
  mention: null,
  mentionPage: (id, title) => set((s) => ({ mention: { id, title, n: (s.mention?.n ?? 0) + 1 } })),
}));

/** Flag `chat-full` on. Its panel is the spark panel, so `chatInPanel` (shell, no share build) decides the rest. */
export const chatFullOn = () => flag("chat-full");
