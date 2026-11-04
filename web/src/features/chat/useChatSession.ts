import { useCallback, useEffect, useRef, useState } from "react";
import { useDataSource } from "@/api";
import { readEvents } from "./sse";
import { applyEvent, dropLastTurn, emptyChat, historyOf, type Chat } from "./thread";
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
  const chatRef = useRef(chat);
  const abortRef = useRef<AbortController | null>(null);
  const metaRef = useRef<{ model: string; backend: string } | null>(null);

  const commit = useCallback((next: Chat) => {
    chatRef.current = next;
    setChat(next);
  }, []);

  useEffect(() => {
    if (!busy) writeJson("session", KEY, chat);
  }, [chat, busy]);

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
    },
    [ds, commit],
  );

  const send = useCallback(
    (question: string, opts: SendOptions) => {
      const q = question.trim();
      if (!q || abortRef.current) return;
      void run(chatRef.current, q, opts);
    },
    [run],
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
    abortRef.current?.abort();
    commit(emptyChat());
  }, [commit]);

  /** A resumed agent session would carry the old scope's pages. */
  const forgetSession = useCallback(() => {
    if (chatRef.current.session) commit({ ...chatRef.current, session: null });
  }, [commit]);

  return { chat, busy, send, regenerate, stop, reset, forgetSession };
}

function patchLast(chat: Chat, f: (m: Chat["messages"][number]) => Chat["messages"][number]): Chat {
  const i = chat.messages.length - 1;
  if (i < 0) return chat;
  return { ...chat, messages: chat.messages.map((m, j) => (j === i ? f(m) : m)) };
}
