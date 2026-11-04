import { useEffect, useRef } from "react";
import { create } from "zustand";
import type { Chat } from "./thread";

/**
 * The chat screen on show, as seen by the Cmd-J quick ask (flag `agent-mode`): while a chat session is mounted,
 * a quick question goes through its `send` (the same path as the main composer) and its answer streams into that chat.
 */
export interface AskHost {
  ask: (question: string) => void;
  chat: Chat;
  busy: boolean;
}

export const useAskHost = create<{ host: AskHost | null }>(() => ({ host: null }));

/** Register the mounted chat session as the quick-ask host; `null` (flag off) registers nothing. */
export function useRegisterAskHost(host: AskHost | null) {
  const ref = useRef(host);
  ref.current = host;
  const on = host !== null;
  const chat = host?.chat;
  const busy = host?.busy ?? false;
  // one overwrite per change (no null frame between two chats' states); cleared only when the screen goes or the flag turns off
  useEffect(() => {
    if (on && chat) useAskHost.setState({ host: { ask: (q) => ref.current?.ask(q), chat, busy } });
  }, [on, chat, busy]);
  useEffect(() => (on ? () => useAskHost.setState({ host: null }) : undefined), [on]);
}
