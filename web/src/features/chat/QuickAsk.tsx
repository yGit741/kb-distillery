import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { MessageSquare, SendHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useDataSource, type ChatStatus, type DataSource } from "@/api";
import { useUi } from "@/app/ui-store";
import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";
import { useFlag } from "@/flags/useFlag";
import { useAskHost } from "./askHost";
import { parsePrompts, pick, systemFor } from "./prompts";
import { STATUS_KEY } from "./SessionPanel";
import { authPayload, authValue, effectiveBackend, parseStatus } from "./status";
import { readJson } from "./storage";
import type { Chat } from "./thread";
import { useChatSession, type SendOptions } from "./useChatSession";

/**
 * Cmd-J quick ask (flag `agent-mode`): the only quick-ask surface. A floating one-line composer that opens on any screen,
 * sends to the current chat session and shows the first lines of the answer, with "Open in chat".
 *
 * On the chat screen the question goes through that screen's own session (`askHost`), so the answer streams into the chat on show.
 * (so it carries that screen's scope and custom-prompt label.) Elsewhere `LocalAsk` runs the same `useChatSession` for the length of the question (it reads the stored chat when it mounts,
 * writes it back when idle) and "Open in chat" waits until the answer is written.
 */

type Prompts = Awaited<ReturnType<DataSource["getChatPrompts"]>>["prompts"];

/**
 * The send options of the main composer, rebuilt from the same status, prompt templates and `kbchat.*` browser settings.
 * (ChatBody builds its own from its UI state; the two must agree. With no chat screen on show there is no scope to carry: unscoped.)
 */
export function quickSendOptions(rawStatus: ChatStatus, rawPrompts: Prompts): SendOptions {
  const view = parseStatus(rawStatus);
  const prompts = parsePrompts(rawPrompts);
  const templateId = readJson("local", "kbchat.template", "query");
  const edits = readJson<Record<string, string>>("local", "kbchat.edits", {});
  const modelPick = readJson("local", "kbchat.model", "");
  const current = pick(prompts, templateId);
  return {
    model: view.models.some((m) => m.id === modelPick) ? modelPick : view.defaultModel,
    backend: effectiveBackend(view),
    scope: "",
    system: systemFor(current, edits),
    auth: authPayload(authValue(view)),
    label: current?.title ?? templateId,
  };
}

/** The last question and its answer, a few lines of it. */
function Answer({ chat, busy, onOpen, canOpen }: { chat: Chat; busy: boolean; onOpen: () => void; canOpen: boolean }) {
  const msgs = chat.messages;
  const bot = msgs[msgs.length - 1];
  const user = msgs[msgs.length - 2];
  if (!bot || bot.role !== "assistant" || !user) return null;
  return (
    <div className="flex flex-col gap-2 border-t px-3 py-2" data-testid="quick-answer">
      <p className="line-clamp-2 break-words text-xs text-muted-foreground">{user.content}</p>
      {bot.content ? (
        <div className="line-clamp-6 text-sm">
          <Markdown>{bot.content}</Markdown>
        </div>
      ) : bot.error ? (
        <p role="alert" className="break-words text-sm text-bad">
          {bot.error}
        </p>
      ) : busy ? (
        <p role="status" className="text-sm text-muted-foreground">
          Thinking…
        </p>
      ) : null}
      <Button variant="ghost" size="sm" className="-mr-1 self-end" onClick={onOpen} disabled={!canOpen}>
        Open in chat
      </Button>
    </div>
  );
}

interface Ask {
  text: string;
  n: number;
}

/** No chat screen on show: a session of our own, mounted only while a quick question needs it. */
function LocalAsk({ ask, sentN, onBusy, onOpen }: { ask: Ask | null; sentN: { current: number }; onBusy: (busy: boolean) => void; onOpen: () => void }) {
  const ds = useDataSource();
  const status = useQuery({ queryKey: STATUS_KEY, queryFn: () => ds.getChatStatus() });
  const prompts = useQuery({ queryKey: ["chat", "prompts"], queryFn: () => ds.getChatPrompts() });
  const { chat, busy, send } = useChatSession();
  useEffect(() => onBusy(busy), [busy, onBusy]);
  useEffect(() => () => onBusy(false), [onBusy]); // unmounting aborts the stream: nothing is running any more
  useEffect(() => {
    if (!ask || ask.n <= sentN.current || !status.data || !prompts.data) return;
    sentN.current = ask.n; // kept by the parent: a remount never asks the same question again
    send(ask.text, quickSendOptions(status.data, prompts.data.prompts));
  }, [ask, status.data, prompts.data, send]);
  if (!ask) return null;
  if (status.isError || prompts.isError) {
    return (
      <p role="alert" className="border-t px-3 py-2 text-sm text-bad">
        The chat service is unreachable.
      </p>
    );
  }
  return <Answer chat={chat} busy={busy} onOpen={onOpen} canOpen={!busy} />;
}

export default function QuickAsk() {
  const on = useFlag("agent-mode");
  return on ? <QuickAskOn /> : null;
}

function QuickAskOn() {
  const open = useUi((s) => s.askOpen);
  const setOpen = useUi((s) => s.setAskOpen);
  const host = useAskHost((s) => s.host);
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const before = useRef<Element | null>(null);
  const [text, setText] = useState("");
  const [sentHere, setSentHere] = useState(false);
  const [local, setLocal] = useState<Ask | null>(null);
  const [localBusy, setLocalBusy] = useState(false);
  const sentN = useRef(0);

  // Cmd-J (Ctrl-J) opens it from anywhere; Esc closes. Nothing else opens it.
  useEffect(() => {
    // another layer on top (the command palette) keeps its own keys
    const otherLayer = () => document.querySelector("[role=dialog]:not([aria-label='Quick ask'])") !== null;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && (e.key.toLowerCase() === "j" || e.code === "KeyJ") && !e.isComposing) {
        e.preventDefault();
        if (otherLayer()) return;
        if (useUi.getState().askOpen) input.current?.focus();
        else setOpen(true);
      } else if (e.key === "Escape" && useUi.getState().askOpen && !e.defaultPrevented && !otherLayer()) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  // opening: a clean panel (unless a question is still running), focus in the box; closing: focus back where it was
  useEffect(() => {
    if (open) {
      before.current = document.activeElement;
      if (!local) setSentHere(false);
      input.current?.focus();
    } else if (before.current instanceof HTMLElement) {
      before.current.focus();
      before.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only the open/close edge matters
  }, [open]);
  // the chat screen came up: it owns the session now, and a local question that was still running was cut off with its hook
  useEffect(() => {
    if (host && local) {
      setLocal(null);
      setLocalBusy(false);
    }
  }, [host, local]);
  // a closed panel with no running question lets go of its session
  useEffect(() => {
    if (!open && !localBusy && local) setLocal(null);
  }, [open, localBusy, local]);

  const busy = host ? host.busy : localBusy;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = text.trim();
    if (!q || busy) return;
    setText("");
    setSentHere(true);
    if (host) host.ask(q);
    else setLocal((cur) => ({ text: q, n: (cur?.n ?? 0) + 1 }));
  };
  const openInChat = () => {
    setOpen(false);
    void navigate({ to: "/chat" as "/" });
  };

  if (!open && !local) return null;
  return (
    <div
      role={open ? "dialog" : undefined}
      aria-label="Quick ask"
      hidden={!open}
      className="fixed left-1/2 top-16 z-50 w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-[var(--shadow)]"
    >
      <form className="flex items-center gap-2 p-2" onSubmit={submit}>
        <MessageSquare aria-hidden className="ml-1 size-4 shrink-0 text-muted-foreground" />
        <input
          ref={input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Ask your knowledge base"
          placeholder={busy ? "Waiting for the answer" : "Ask your knowledge base"}
          className="h-8 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
        <Button type="submit" variant="ghost" size="icon" className="size-8" aria-label="Send" disabled={!text.trim() || busy}>
          <SendHorizontal aria-hidden />
        </Button>
        <Button type="button" variant="ghost" size="icon" className="size-8" aria-label="Close quick ask" onClick={() => setOpen(false)}>
          <X aria-hidden />
        </Button>
      </form>
      {host
        ? sentHere && <Answer chat={host.chat} busy={host.busy} onOpen={openInChat} canOpen />
        : local && <LocalAsk ask={local} sentN={sentN} onBusy={setLocalBusy} onOpen={openInChat} />}
      <p className="border-t px-3 py-1.5 text-xs text-muted-foreground">Enter to send, Esc to close.</p>
    </div>
  );
}
