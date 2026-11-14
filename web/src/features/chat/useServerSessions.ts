import { useEffect, useMemo, useRef } from "react";
import { useDataSource } from "@/api";
import { DELETED_EVENT, FAILED_EVENT, OPEN_EVENT, SYNCED_EVENT, chatIdOf, createMirror, fromDoc, migrateBrowserChat, serverSessionsOn, sessionBus, setChatBusy, type SessionMeta } from "./serverStorage";
import type { Chat } from "./thread";

/**
 * The server-side half of `useChatSession` (the live local backend): mirrors the chat after each finished turn, copies the
 * browser-held chat once on first load, and lets the past-chats list open a stored chat. A share build: no effect runs.
 */
export function useServerSessions(chat: Chat, busy: boolean, meta: SessionMeta | null, open: (c: Chat) => void) {
  const ds = useDataSource();
  const on = serverSessionsOn(ds);
  const mirror = useMemo(() => createMirror(ds, {
    onSynced: (id) => sessionBus.dispatchEvent(new CustomEvent(SYNCED_EVENT, { detail: id })),
    onError: (id, message) => sessionBus.dispatchEvent(new CustomEvent(FAILED_EVENT, { detail: { id, message } })),
  }), [ds]);
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

  // a tab closed or reloaded inside the quiet period still sends the last turn
  useEffect(() => {
    if (!on) return;
    const h = () => void mirror.flush();
    window.addEventListener("pagehide", h);
    return () => window.removeEventListener("pagehide", h);
  }, [on, mirror]);

  // a deleted chat must not be recreated by a save that was still waiting
  useEffect(() => {
    if (!on) return;
    const h = (e: Event) => mirror.cancel(chatIdOf((e as CustomEvent<string>).detail));
    sessionBus.addEventListener(DELETED_EVENT, h);
    return () => sessionBus.removeEventListener(DELETED_EVENT, h);
  }, [on, mirror]);

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
