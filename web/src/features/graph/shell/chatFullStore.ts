import { create } from "zustand";
import { flag } from "@/flags";
import { readJson, writeJson } from "@/features/chat/storage";

/**
 * Size of the one chat surface (flag `chat-full`): `panel` is the left panel beside the graph, `full` the three
 * columns (chat list, chat, graph with a mini explorer). Whether the list shows and whether the right pane is
 * folded to a rail are remembered per browser; the size itself is not (a reload opens the panel).
 */
const LIST_KEY = "kbchat.full.list";
const FOLD_KEY = "kbchat.full.folded";

interface ChatFullState {
  full: boolean;
  listOpen: boolean;
  folded: boolean;
  setFull: (full: boolean) => void;
  toggleList: () => void;
  setFolded: (folded: boolean) => void;
  /** Page ids of the graph, so the composer's @ can complete them (set by the graph screen). */
  pages: readonly { id: string; title: string }[];
  setPages: (pages: readonly { id: string; title: string }[]) => void;
  /** Slugs the last answer cited, newest answer only (the mini explorer lists them). */
  cited: readonly string[];
  setCited: (cited: readonly string[]) => void;
  /** A page the graph handed to the composer (a click on a node): `n` makes the same page insert twice. */
  mention: { id: string; title: string; n: number } | null;
  mentionPage: (id: string, title: string) => void;
}

export const useChatFull = create<ChatFullState>((set, get) => ({
  full: false,
  listOpen: readJson("local", LIST_KEY, true),
  folded: readJson("local", FOLD_KEY, false),
  setFull: (full) => set({ full }),
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
  mention: null,
  mentionPage: (id, title) => set((s) => ({ mention: { id, title, n: (s.mention?.n ?? 0) + 1 } })),
}));

/** Flag `chat-full` on. Its panel is the spark panel, so `chatInPanel` (shell, no share build) decides the rest. */
export const chatFullOn = () => flag("chat-full");
