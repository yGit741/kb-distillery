import { readJson, writeJson } from "@/features/chat/storage";
import { emptyChat, type Chat } from "@/features/chat/thread";
import { flag } from "@/flags";
import { useChatDock } from "../../tools/chatDockStore";
import { useSparkPanel } from "../sparkPanelStore";
import { getSession, type Fetcher, type SessionRow } from "./api";

/** The chat the browser holds (the chat screen keeps exactly one, in sessionStorage). */
const CHAT_KEY = "kbchat.chat";

const TITLE_MAX = 70;

/** The browser-held chat as one row, or none when it has no messages yet. Used when the server has no session store. */
export function browserSessions(): SessionRow[] {
  const c = readJson<Chat | null>("session", CHAT_KEY, null);
  if (!c || !Array.isArray(c.messages) || !c.messages.length) return [];
  const first = c.messages.find((m) => m.role === "user")?.content.trim() ?? "";
  const title = first.length > TITLE_MAX ? `${first.slice(0, TITLE_MAX - 1)}...` : first;
  return [{ id: c.id, title: title || "Current chat" }];
}

/**
 * Show the chat dock on a freshly loaded chat. The dock reads its chat when it mounts, so an already open dock is
 * closed and opened again in the next tick.
 */
export function showDock(): void {
  // flag `spark-chat`: the chat opens in the left panel, and the right dock stays shut
  if (flag("spark-chat")) {
    useChatDock.getState().set({ open: false });
    useSparkPanel.getState().show();
    return;
  }
  const dock = useChatDock.getState();
  if (!dock.open) {
    dock.set({ open: true });
    return;
  }
  dock.set({ open: false });
  setTimeout(() => useChatDock.getState().set({ open: true }), 0);
}

/** Resume a saved chat in the dock: a server session is copied into the browser's chat slot first. */
export async function resumeSession(f: Fetcher, row: SessionRow, fromServer: boolean): Promise<void> {
  if (fromServer) {
    const doc = await getSession(f, row.id);
    const chat: Chat = { id: `kb-chat:${row.id.replace(/^kb-chat:/, "")}`, session: null, messages: doc.messages as Chat["messages"] };
    writeJson("session", CHAT_KEY, chat);
  }
  showDock();
}

/** A new, empty chat in the dock. */
export function newChat(): void {
  writeJson("session", CHAT_KEY, emptyChat());
  showDock();
}
