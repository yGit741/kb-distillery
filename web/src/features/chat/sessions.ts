import { readJson, writeJson } from "./storage";
import { chatTitle, type Chat, type ChatMessage } from "./thread";

/** Resumable agent sessions, kept in this browser: a chat that has a session id can be picked up again. */
export interface SessionEntry {
  id: string;
  session: string;
  title: string;
  /** epoch ms of the last activity */
  last: number;
  messages: ChatMessage[];
}

const KEY = "kbchat.sessions";
export const MAX_SESSIONS = 12;

export const loadSessions = (): SessionEntry[] => {
  const v = readJson<SessionEntry[]>("local", KEY, []);
  return Array.isArray(v) ? v.filter((e) => e && typeof e.session === "string" && Array.isArray(e.messages)) : [];
};

/** Newest first, one entry per chat, capped. Only the words are kept (no trace, thinking or usage). */
export function upsertSession(list: SessionEntry[], chat: Chat, now = Date.now()): SessionEntry[] {
  if (!chat.session || !chat.messages.some((m) => m.role === "assistant" && m.content)) return list;
  const entry: SessionEntry = {
    id: chat.id,
    session: chat.session,
    title: chatTitle(chat.messages),
    last: now,
    messages: chat.messages.filter((m) => !m.failed).map(({ role, content, sources }) => ({ role, content, sources })),
  };
  return [entry, ...list.filter((e) => e.id !== chat.id)].slice(0, MAX_SESSIONS);
}

export const saveSessions = (list: SessionEntry[]) => writeJson("local", KEY, list);

export function ago(ts: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}
