import { useQuery } from "@tanstack/react-query";
import { Mic, Plus, SendHorizontal, Square, X } from "lucide-react";
import { useChatDock } from "../tools/chatDockStore";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { useDataSource } from "@/api";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ComposerLine } from "@/features/chat/ComposerLine";
import { MessageList } from "@/features/chat/MessageList";
import { parsePrompts } from "@/features/chat/prompts";
import { quickSendOptions } from "@/features/chat/QuickAsk";
import { STATUS_KEY } from "@/features/chat/SessionPanel";
import { backendLabel, effectiveBackend, parseStatus } from "@/features/chat/status";
import { readJson, writeJson } from "@/features/chat/storage";
import { chatTitle, type ChatMessage } from "@/features/chat/thread";
import { useChatSession } from "@/features/chat/useChatSession";
import { citedSlugs, slugOfHref } from "./cites";
import { useCites } from "./citeStore";
import { SPARK_PANEL_W } from "./layout";
import { useSparkPanel } from "./sparkPanelStore";

/**
 * The left chat panel (flag `spark-chat`): the chat opened from the spark corner, beside the graph. It runs the same
 * `useChatSession` as the chat screen and the right dock, so the stored chat, models and billing are shared.
 */
export function SparkPanel({ scope }: { scope?: string }) {
  const close = useSparkPanel((s) => s.close);
  const ds = useDataSource();
  const status = useQuery({ queryKey: STATUS_KEY, queryFn: () => ds.getChatStatus() });
  const promptsQ = useQuery({ queryKey: ["chat", "prompts"], queryFn: () => ds.getChatPrompts() });
  return (
    <aside
      aria-label="Chat"
      data-testid="spark-panel"
      className="spark-panel-in pointer-events-auto absolute inset-y-0 left-0 z-40 flex max-w-full flex-col border-r bg-card text-card-foreground shadow-[var(--shadow)]"
      style={{ width: SPARK_PANEL_W }}
      onKeyDown={(e) => {
        // Escape anywhere in the panel closes it, and stops here: the graph's own Escape (selection, reader) waits
        if (e.key === "Escape" && !e.defaultPrevented) {
          e.stopPropagation();
          close();
        }
      }}
    >
      {status.isPending || promptsQ.isPending ? (
        <>
          <Header title="New chat" onClose={close} />
          <div className="p-4">
            <Loading label="Loading chat" rows={3} />
          </div>
        </>
      ) : status.isError || promptsQ.isError ? (
        <>
          <Header title="New chat" onClose={close} />
          <div className="p-4">
            <ErrorState title="The chat service is unreachable" error={status.error ?? promptsQ.error} onRetry={() => void Promise.all([status.refetch(), promptsQ.refetch()])} />
          </div>
        </>
      ) : (
        <Body status={status.data} prompts={promptsQ.data.prompts} scope={scope ?? ""} onClose={close} />
      )}
    </aside>
  );
}

function Header({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <header className="flex items-start gap-2 border-b px-5 py-3">
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-[15px] font-semibold" data-testid="spark-title">
          {title}
        </h2>
        <p className="text-xs text-muted-foreground">knows the graph you are looking at</p>
      </div>
      <Button variant="ghost" size="icon" className="-mr-2 size-8" aria-label="Close chat" onClick={onClose}>
        <X aria-hidden strokeWidth={1.6} />
      </Button>
    </header>
  );
}

/**
 * The pages the answer on screen cites, lit on the graph (./citeStore). The answer on screen is the newest one until the
 * reader scrolls another into the middle. The graph frames the cited pages once when an answer finishes or the chat
 * opens, never on a render; a click on a lit page scrolls here to the sentence that cites it.
 */
function useCitedPages(scroller: RefObject<HTMLDivElement | null>, messages: ChatMessage[], busy: boolean) {
  const [pick, setPick] = useState<{ n: number; idx: number | null }>({ n: messages.length, idx: null });
  const lastAssistant = (() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i]!.role === "assistant") return i;
    return -1;
  })();
  // a new message takes the screen again
  const idx = pick.n === messages.length && pick.idx !== null ? pick.idx : lastAssistant;
  const settled = !(busy && idx === messages.length - 1);
  const slugs = useMemo(() => (idx >= 0 && settled ? citedSlugs(messages[idx]!.content) : []), [messages, idx, settled]);

  useEffect(() => {
    useCites.getState().setSlugs(slugs);
  }, [slugs]);
  useEffect(() => () => useCites.getState().clear(), []);

  // frame the cited pages when an answer finishes and when the chat opens with one
  const framed = useRef("");
  useEffect(() => {
    const key = slugs.length ? `${messages.length}:${idx}` : "";
    if (key && key !== framed.current) useCites.getState().refit();
    framed.current = key;
  }, [slugs, messages.length, idx]);

  // the answer in the middle of the panel is the one on screen
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    let t = 0;
    const onScroll = () => {
      window.clearTimeout(t);
      t = window.setTimeout(() => {
        const box = el.getBoundingClientRect();
        const mid = box.top + box.height / 2;
        const items = [...el.querySelectorAll<HTMLElement>("li[data-role]")];
        const at = items.findIndex((li) => {
          const r = li.getBoundingClientRect();
          return r.top <= mid && r.bottom >= mid;
        });
        if (at >= 0 && items[at]!.dataset.role === "assistant") setPick({ n: messages.length, idx: at });
      }, 120);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.clearTimeout(t);
      el.removeEventListener("scroll", onScroll);
    };
  }, [scroller, messages.length]);

  // a click on a lit page: scroll to the sentence that cites it, and mark it for a moment
  const req = useCites((s) => s.scrollReq);
  useEffect(() => {
    const el = scroller.current;
    if (!req || !el) return;
    const li = el.querySelectorAll<HTMLElement>("li[data-role]")[idx];
    const link = [...(li?.querySelectorAll<HTMLAnchorElement>("a") ?? [])].find((a) => slugOfHref(a.getAttribute("href")) === req.slug);
    const line = link?.closest<HTMLElement>("p, li") ?? link;
    if (!line) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    line.scrollIntoView?.({ block: "center", behavior: still ? "auto" : "smooth" });
    line.setAttribute("data-cited-now", "");
    const t = window.setTimeout(() => line.removeAttribute("data-cited-now"), 1800);
    return () => window.clearTimeout(t);
  }, [req, idx, scroller]);

  return slugs;
}

type Status = Parameters<typeof parseStatus>[0];
type Prompts = Parameters<typeof parsePrompts>[0];

function Body({ status, prompts, scope, onClose }: { status: Status; prompts: Prompts; scope: string; onClose: () => void }) {
  const { chat, busy, send, regenerate, answer, stop } = useChatSession();
  const view = useMemo(() => parseStatus(status), [status]);
  const [modelPick, setModelPick] = useState(() => readJson("local", "kbchat.model", ""));
  // a question handed in from Ask or the search ("/") prefills the box once
  const [text, setText] = useState(() => {
    const q = useChatDock.getState().question;
    if (q) useChatDock.setState({ question: "" });
    return q;
  });
  const box = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const cited = useCitedPages(scroller, chat.messages, busy);
  const model = view.models.some((m) => m.id === modelPick) ? modelPick : view.defaultModel;
  const options = () => ({ ...quickSendOptions(status, prompts), model, scope });
  const title = chat.messages.length ? chatTitle(chat.messages) : "New chat";
  const chip = backendLabel(view);

  useEffect(() => box.current?.focus(), []);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const q = text.trim();
    if (!q) return;
    send(q, options());
    setText("");
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <>
      <Header title={title} onClose={onClose} />
      <div ref={scroller} className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4 [&_[data-cited-now]]:rounded-sm [&_[data-cited-now]]:bg-primary/10 [&_[data-cited-now]]:transition-colors [&_li[data-testid=tool-line]]:w-fit [&_li[data-testid=tool-line]]:max-w-full [&_li[data-testid=tool-line]]:rounded-md [&_li[data-testid=tool-line]]:bg-secondary/60 [&_li[data-testid=tool-line]]:px-2 [&_li[data-testid=tool-line]]:py-0.5">
        {chat.messages.length === 0 ? (
          <p className="text-sm text-muted-foreground">Ask about the pages on the graph. The agent searches and reads your wiki, read-only, and cites what it opened.</p>
        ) : (
          <MessageList messages={chat.messages} busy={busy} onRegenerate={() => regenerate(options())} onAnswer={answer} />
        )}
      </div>
      {cited.length > 0 && (
        <p className="px-5 pb-1 text-xs text-muted-foreground" data-testid="spark-cites">
          {cited.length} cited page{cited.length === 1 ? "" : "s"} lit on the graph
        </p>
      )}
      <div className="flex flex-col gap-2 px-4 pb-4 pt-2">
        <form onSubmit={submit} className="flex items-end gap-1 rounded-[20px] border bg-background px-2 py-1.5 focus-within:ring-2 focus-within:ring-ring">
          <Button type="button" variant="ghost" size="icon" className="size-8 shrink-0 rounded-full" aria-label="Attach" title="Attach, coming soon">
            <Plus aria-hidden strokeWidth={1.6} />
          </Button>
          <textarea
            ref={box}
            rows={1}
            aria-label="Your message"
            placeholder="Type / for commands"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
            className="max-h-32 min-h-8 min-w-0 flex-1 resize-none bg-transparent py-1.5 text-sm outline-none placeholder:text-muted-foreground"
          />
          <Button type="button" variant="ghost" size="icon" className="size-8 shrink-0 rounded-full" aria-label="Voice input" title="Voice input is not available yet" disabled>
            <Mic aria-hidden strokeWidth={1.6} />
          </Button>
          {busy ? (
            <Button type="button" variant="ghost" size="icon" className="size-8 shrink-0 rounded-full" aria-label="Stop" onClick={stop}>
              <Square aria-hidden strokeWidth={1.6} />
            </Button>
          ) : (
            <Button type="submit" variant="ghost" size="icon" className="size-8 shrink-0 rounded-full" aria-label="Send" disabled={!text.trim()}>
              <SendHorizontal aria-hidden strokeWidth={1.6} />
            </Button>
          )}
        </form>
        {effectiveBackend(view) === "agent" ? (
          <ComposerLine
            account={view.authMode === "api_key" && view.keyLoaded ? "api" : "subscription"}
            models={view.models}
            model={model}
            onModel={(id) => {
              setModelPick(id);
              writeJson("local", "kbchat.model", id);
            }}
          />
        ) : (
          <p className="text-xs text-muted-foreground">{chip.text}</p>
        )}
      </div>
    </>
  );
}
