/**
 * Server-side chat sessions (every local kb, in `<kb>/.local/sessions/`): the open chat is mirrored to `PUT /api/sessions/{id}` after every
 * completed turn, so past chats live in one place (`<kb>/.local/sessions/`) instead of one browser tab.
 *
 * The browser still holds the open chat while it streams (`useChatSession`); this file only copies finished turns out
 * and reads them back. With the flag off nothing here runs and the browser path in `storage.ts` is the only one.
 * Every browser-storage access is guarded; a failed request never breaks the chat (the next turn sends the whole
 * document again).
 */
import type { DataSource, SessionPutRequest } from "@/api";
import { IS_SHARE } from "@/share/env";
import { readJson, writeJson } from "./storage";
import type { Chat } from "./thread";

/** The open chat lives in sessionStorage under this key (`useChatSession`). */
export const CHAT_KEY = "kbchat.chat";
/** localStorage marker: the browser-held chat has been copied to the server. */
export const MIGRATED_KEY = "kbchat.sessions.migrated";
export const MIRROR_DELAY_MS = 800;

/** Server sessions exist only on the live local backend (never in a share build): each kb keeps its own chats. */
export const serverSessionsOn = (ds: DataSource): boolean => ds.kind === "http" && !IS_SHARE;

/** `kb-chat:20261103101500-abc123` <-> `20261103101500-abc123` (the server id is a plain slug). */
export const sessionIdOf = (chatId: string): string => chatId.replace(/^kb-chat:/, "");
export const chatIdOf = (sessionId: string): string => `kb-chat:${sessionId}`;

/** ISO time encoded in a chat id (`newChatId`), or undefined for an id of another shape. */
export function createdOf(chatId: string): string | undefined {
  const m = /^(?:kb-chat:)?(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})-/.exec(chatId);
  if (!m) return undefined;
  const iso = `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`;
  return Number.isNaN(Date.parse(iso)) ? undefined : iso;
}

export interface SessionMeta {
  model?: string;
  effort?: string;
  backend?: string;
}

/** The document the server stores for a chat. No title: the server keeps the stored one (or takes the first question). */
export function toDoc(chat: Chat, meta: SessionMeta = {}): SessionPutRequest {
  return {
    messages: chat.messages as unknown as SessionPutRequest["messages"],
    created: createdOf(chat.id),
    ...(meta.model ? { model: meta.model } : {}),
    ...(meta.effort ? { effort: meta.effort } : {}),
    ...(meta.backend ? { backend: meta.backend } : {}),
  };
}

/** A stored document as the chat screen keeps it. `session` (the agent's resume id) is not stored: a reopened chat
 *  starts a fresh agent session and sends its history. */
export function fromDoc(doc: { id: string; messages: unknown[] }): Chat {
  return { id: chatIdOf(doc.id), session: null, messages: doc.messages as Chat["messages"] };
}

export interface Mirror {
  /** Remember the newest state of a chat and send it after the quiet period (one request per chat). */
  schedule(chat: Chat, meta?: SessionMeta): void;
  /** Send whatever is pending now. */
  flush(): Promise<void>;
  /** Drop what is pending for a chat (it was deleted). */
  cancel(chatId: string): void;
}

/** Debounced, ordered mirror: requests go one after another, so a slow older save never lands after a newer one. */
export function createMirror(
  ds: Pick<DataSource, "putSession">,
  opts: { delayMs?: number; onSynced?: (id: string) => void; onError?: (id: string, message: string) => void } = {},
): Mirror {
  const delay = opts.delayMs ?? MIRROR_DELAY_MS;
  const pending = new Map<string, { chat: Chat; meta?: SessionMeta }>();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let chain: Promise<void> = Promise.resolve();

  const drain = () => {
    timer = undefined;
    const batch = [...pending.entries()];
    pending.clear();
    for (const [id, { chat, meta }] of batch) {
      chain = chain.then(async () => {
        try {
          await ds.putSession(id, toDoc(chat, meta));
          opts.onSynced?.(id);
        } catch (e) {
          // offline or read-only server: the next turn sends the whole chat again; the list says so meanwhile
          opts.onError?.(id, e instanceof Error ? e.message : String(e));
        }
      });
    }
    return chain;
  };

  return {
    schedule(chat, meta) {
      if (!chat.messages.length) return;
      pending.set(sessionIdOf(chat.id), { chat, meta });
      if (timer !== undefined) clearTimeout(timer);
      timer = setTimeout(drain, delay);
    },
    flush() {
      if (timer !== undefined) clearTimeout(timer);
      return drain();
    },
    cancel(chatId) {
      pending.delete(sessionIdOf(chatId));
    },
  };
}

/**
 * Copy the chat this browser tab holds to the server, once. Idempotent: the marker is set only after the server
 * accepted it (or there was nothing to copy), and a chat that is already marked is never sent again.
 * Returns true when a chat was sent now.
 */
export async function migrateBrowserChat(ds: Pick<DataSource, "putSession">, meta: SessionMeta = {}): Promise<boolean> {
  if (readJson<boolean>("local", MIGRATED_KEY, false)) return false;
  const c = readJson<Chat | null>("session", CHAT_KEY, null);
  if (c && typeof c.id === "string" && Array.isArray(c.messages) && c.messages.length) {
    try {
      await ds.putSession(sessionIdOf(c.id), toDoc(c, meta));
    } catch {
      return false; // try again on the next load
    }
    writeJson("local", MIGRATED_KEY, true);
    return true;
  }
  writeJson("local", MIGRATED_KEY, true);
  return false;
}

/** Between `PastChats` and `useChatSession`, so neither needs a prop through the screen. */
export const sessionBus = new EventTarget();
export const OPEN_EVENT = "open";
export const SYNCED_EVENT = "synced";
export const FAILED_EVENT = "failed";
export const DELETED_EVENT = "deleted";

let busy = false;
const busyListeners = new Set<() => void>();
/** Whether the open chat is streaming (a stored chat is not opened under a stream). */
export function setChatBusy(b: boolean): void {
  if (busy === b) return;
  busy = b;
  for (const fn of busyListeners) fn();
}
export const subscribeChatBusy = (fn: () => void): (() => void) => {
  busyListeners.add(fn);
  return () => busyListeners.delete(fn);
};
export const chatBusy = (): boolean => busy;
