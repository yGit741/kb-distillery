import { create } from "zustand";

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
  ask: (question) => set({ open: true, question }),
  set: (s) => set(s),
}));

/** A question draft about the selected pages: their wikilinks, so the agent reads exactly those first. */
export function askAbout(pages: readonly { id: string }[], max = 12): string {
  const links = pages.slice(0, max).map((p) => `[[${p.id}]]`).join(", ");
  const more = pages.length > max ? ` (and ${pages.length - max} more)` : "";
  return `About ${links}${more}: `;
}
