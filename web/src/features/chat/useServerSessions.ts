import { useEffect, useMemo, useRef } from "react";
import { useDataSource } from "@/api";
import { useFlag } from "@/flags/useFlag";
import { OPEN_EVENT, SYNCED_EVENT, createMirror, fromDoc, migrateBrowserChat, serverSessionsOn, sessionBus, setChatBusy, type SessionMeta } from "./serverStorage";
import type { Chat } from "./thread";

/**
 * The server-side half of `useChatSession` (flag `agent-mode`): mirrors the chat after each finished turn, copies the
 * browser-held chat once on first load, and lets the past-chats list open a stored chat. Flag off: no effect runs.
 */
export function useServerSessions(chat: Chat, busy: boolean, meta: SessionMeta | null, open: (c: Chat) => void) {
  const ds = useDataSource();
  const on = useFlag("agent-mode") && serverSessionsOn(ds);
  const mirror = useMemo(() => createMirror(ds, { onSynced: (id) => sessionBus.dispatchEvent(new CustomEvent(SYNCED_EVENT, { detail: id })) }), [ds]);
  const first = useRef(chat);
  const metaRef = useRef(meta);
  metaRef.current = meta;

  useEffect(() => {
    if (on) void migrateBrowserChat(ds, metaRef.current ?? {});
  }, [on, ds]);

  // a finished turn (not the chat as loaded, not while streaming) goes to the server after a quiet moment
  useEffect(() => {
    if (!on || busy || chat === first.current) return;
    mirror.schedule(chat, metaRef.current ?? undefined);
  }, [on, busy, chat, mirror]);

  useEffect(() => () => void mirror.flush(), [mirror]);

  useEffect(() => {
    if (!on) return;
    setChatBusy(busy);
    return () => setChatBusy(false);
  }, [on, busy]);

  useEffect(() => {
    if (!on) return;
    const h = (e: Event) => {
      void mirror.flush();
      const opened = fromDoc((e as CustomEvent<{ id: string; messages: unknown[] }>).detail);
      first.current = opened; // opening is not a change: it must not re-save the chat and move it to the top
      open(opened);
    };
    sessionBus.addEventListener(OPEN_EVENT, h);
    return () => sessionBus.removeEventListener(OPEN_EVENT, h);
  }, [on, mirror, open]);
}
