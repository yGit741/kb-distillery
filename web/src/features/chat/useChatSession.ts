import { useCallback, useEffect, useRef, useState } from "react";
import { useDataSource } from "@/api";
import { useFlag } from "@/flags/useFlag";
import { readEvents } from "./sse";
import { applyEvent, dropLastTurn, emptyChat, historyOf, type Chat } from "./thread";
import { loadSessions, saveSessions, upsertSession, type SessionEntry } from "./sessions";
import { readJson, writeJson } from "./storage";
import { useServerSessions } from "./useServerSessions";

export interface SendOptions {
  model: string;
  backend: "agent" | "direct";
  scope: string;
  system: string;
  auth: { auth_mode: string; active_key?: string };
  /** appended to the answer's meta line (template title, custom flag) */
  label: string;
}

const KEY = "kbchat.chat";

function load(): Chat {
  const c = readJson<Chat | null>("session", KEY, null);
  return c && Array.isArray(c.messages) ? { id: c.id, session: c.session ?? null, messages: c.messages } : emptyChat();
}

/** The conversation and its stream: send, stop, regenerate, new chat. Aborts the stream on unmount. */
export function useChatSession() {
  const ds = useDataSource();
  const [chat, setChat] = useState<Chat>(load);
  const [busy, setBusy] = useState(false);
  const agentMode = useFlag("agent-mode");
  const chatRef = useRef(chat);
  const resumeRef = useRef<{ text: string; opts: SendOptions } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const metaRef = useRef<{ model: string; backend: string } | null>(null);

  const commit = useCallback((next: Chat) => {
    chatRef.current = next;
    setChat(next);
  }, []);

  useEffect(() => {
    if (!busy) writeJson("session", KEY, chat);
  }, [chat, busy]);

  // agent mode: finished chats with a session id stay resumable from the Session panel
  const [sessions, setSessions] = useState<SessionEntry[]>(() => (agentMode ? loadSessions() : []));
  useEffect(() => {
    if (!agentMode || busy) return;
    setSessions((cur) => {
      const next = upsertSession(cur, chat);
      if (next !== cur) saveSessions(next);
      return next;
    });
  }, [agentMode, chat, busy]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const open = useCallback((c: Chat) => {
    if (!abortRef.current) commit(c); // never swap the chat under a stream
  }, [commit]);
  useServerSessions(chat, busy, metaRef.current, open); // flag `agent-mode`: no-op while it is off

  const run = useCallback(
    async (base: Chat, question: string, opts: SendOptions) => {
      const history = historyOf(base.messages);
      metaRef.current = { model: opts.model, backend: opts.backend };
      commit({
        ...base,
        todo: undefined,
        messages: [...base.messages, { role: "user", content: question, sources: [] }, { role: "assistant", content: "" }],
      });
      const ctl = new AbortController();
      abortRef.current = ctl;
      setBusy(true);
      let usageSeen = false;
      let stopped = false;
      try {
        const res = await ds.chatStream(
          {
            question,
            history,
            model: opts.model,
            backend: opts.backend,
            scope: opts.scope || undefined,
            session: base.session,
            system: opts.system,
            ...opts.auth,
          },
          ctl.signal,
        );
        if (!res.body) throw new Error("The server sent no stream.");
        await readEvents(
          res.body,
          (events) => {
            let next = chatRef.current;
            for (const ev of events) {
              if (ev.type === "usage") usageSeen = true;
              next = applyEvent(next, ev);
            }
            commit(next);
          },
          ctl.signal,
        );
      } catch (e) {
        if (ctl.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) stopped = true;
        else {
          const msg = e instanceof Error ? e.message : String(e);
          commit(patchLast(chatRef.current, (m) => ({ ...m, error: m.error ?? msg })));
        }
      } finally {
        if (abortRef.current === ctl) abortRef.current = null;
        setBusy(false);
      }
      const cur = chatRef.current;
      const last = cur.messages.length - 1;
      const bot = cur.messages[last];
      if (!bot || bot.role !== "assistant") return;
      let meta = bot.meta;
      if (stopped) meta = "stopped";
      else if (usageSeen) {
        meta = [opts.label, opts.model, opts.backend === "agent" ? `agent${bot.usage?.num_turns ? `, ${bot.usage.num_turns} turns` : ""}` : "", bot.notice]
          .filter(Boolean)
          .join(" · ");
      }
      const failedTurn = !!bot.error && !bot.content;
      let next = patchLast(cur, (m) => ({ ...m, meta }));
      if (failedTurn) {
        next = { ...next, messages: next.messages.map((m, i) => (i === last - 1 ? { ...m, failed: true } : m)) };
      }
      commit(next);
      // a mid-turn message that could not be queued: the turn was stopped, now resume the session with it
      const again = resumeRef.current;
      resumeRef.current = null;
      if (again) void run(chatRef.current, again.text, again.opts);
    },
    [ds, commit],
  );

  /** Agent mode, a message while the turn runs: queued into the live client; if that fails, stop + resume with it. */
  const queueMidTurn = useCallback(
    async (text: string, opts: SendOptions) => {
      const session = chatRef.current.session;
      if (session) {
        try {
          await ds.sendChatMessage({ session, text });
          return;
        } catch {
          /* no live turn to take it: fall through */
        }
      }
      if (!abortRef.current) return;
      resumeRef.current = { text, opts };
      abortRef.current.abort();
    },
    [ds],
  );

  const send = useCallback(
    (question: string, opts: SendOptions) => {
      const q = question.trim();
      if (!q) return;
      if (abortRef.current) {
        if (agentMode && opts.backend === "agent") void queueMidTurn(q, opts);
        return;
      }
      void run(chatRef.current, q, opts);
    },
    [run, agentMode, queueMidTurn],
  );

  const regenerate = useCallback(
    (opts: SendOptions) => {
      if (abortRef.current) return;
      const { chat: base, question } = dropLastTurn(chatRef.current);
      if (question) void run(base, question, opts);
    },
    [run],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(() => {
    resumeRef.current = null;
    abortRef.current?.abort();
    commit(emptyChat());
  }, [commit]);

  /** Pick up a stored session: its words come back and the next message resumes it on the server. */
  const resume = useCallback(
    (entry: SessionEntry) => {
      resumeRef.current = null;
      abortRef.current?.abort();
      commit({ id: entry.id, session: entry.session, messages: entry.messages });
    },
    [commit],
  );

  /** A resumed agent session would carry the old scope's pages. */
  const forgetSession = useCallback(() => {
    if (chatRef.current.session) commit({ ...chatRef.current, session: null });
  }, [commit]);

  return { chat, busy, send, regenerate, stop, reset, forgetSession, sessions, resume };
}

function patchLast(chat: Chat, f: (m: Chat["messages"][number]) => Chat["messages"][number]): Chat {
  const i = chat.messages.length - 1;
  if (i < 0) return chat;
  return { ...chat, messages: chat.messages.map((m, j) => (j === i ? f(m) : m)) };
}
