import { create } from "zustand";

import { link } from "@/lib/links";
import { chatInPanel, useSparkPanel } from "../shell/sparkPanelStore";

/**
 * State of the chat dock (the research chat next to the graph). Kept apart from ChatDock.tsx so the finder,
 * the palette and the selection pill can open it without pulling the chat screen into share builds.
 */
interface ChatDockState {
  open: boolean;
  wide: boolean;
  /** The last question handed in ("/" in the finder, Ask on a selection); ChatScreen prefills it. */
  question: string;
  ask: (question: string) => void;
  set: (s: Partial<Pick<ChatDockState, "open" | "wide">>) => void;
}

export const useChatDock = create<ChatDockState>((set) => ({
  open: false,
  wide: false,
  question: "",
  // flag spark-chat: the dock stays shut and the left panel opens instead (one chat on screen, never two)
  ask: (question) => {
    if (chatInPanel()) {
      set({ open: false, question });
      useSparkPanel.getState().show();
    } else set({ open: true, question });
  },
  set: (s) => {
    if (s.open && chatInPanel()) {
      set({ ...s, open: false });
      useSparkPanel.getState().show();
    } else set(s);
  },
}));

/** A question draft about the selected pages: their page links, so the agent reads exactly those first. */
export function askAbout(pages: readonly { id: string }[], max = 12): string {
  const links = pages.slice(0, max).map((p) => link(p.id)).join(", ");
  const more = pages.length > max ? ` (and ${pages.length - max} more)` : "";
  return `About ${links}${more}: `;
}
