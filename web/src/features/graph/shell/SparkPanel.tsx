import { useQuery } from "@tanstack/react-query";
import { Maximize2, Minimize2, PanelLeft, SlidersHorizontal, X } from "lucide-react";
import { useChatDock } from "../tools/chatDockStore";
import { useEffect, useMemo, useRef, useState } from "react";
import { useDataSource } from "@/api";
import { useFlag } from "@/flags/useFlag";
import { IS_SHARE } from "@/share/env";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ComposerLine } from "@/features/chat/ComposerLine";
import { cn } from "@/lib/utils";
import { MessageList } from "@/features/chat/MessageList";
import { parsePrompts } from "@/features/chat/prompts";
import { quickSendOptions } from "@/features/chat/QuickAsk";
import { STATUS_KEY } from "@/features/chat/SessionPanel";
import { backendLabel, effectiveBackend, parseStatus } from "@/features/chat/status";
import { readJson, writeJson } from "@/features/chat/storage";
import { chatTitle } from "@/features/chat/thread";
import { useChatSession } from "@/features/chat/useChatSession";
import { sessionIdOf } from "@/features/chat/serverStorage";
import { ChatList } from "./ChatList";
import { ChatTools } from "./ChatTools";
import { useChatFull } from "./chatFullStore";
import { FULL_LIST_W, chatPanelWidth } from "./layout";
import { SparkComposer } from "./SparkComposer";
import { useSparkPanel } from "./sparkPanelStore";

/**
 * The left chat panel (flag `spark-chat`): the chat opened from the spark corner, beside the graph. It runs the same
 * `useChatSession` as the chat screen and the right dock, so the stored chat, models and billing are shared.
 */
export function SparkPanel({ scope }: { scope?: string }) {
  const closePanel = useSparkPanel((s) => s.close);
  const close = () => {
    useChatFull.getState().setFull(false);
    closePanel();
  };
  const ds = useDataSource();
  const rich = useFlag("chat-full");
  const sizeFull = useChatFull((s) => s.full);
  const full = rich && sizeFull;
  const folded = useChatFull((s) => s.folded);
  const listOpen = useChatFull((s) => s.listOpen);
  const status = useQuery({ queryKey: STATUS_KEY, queryFn: () => ds.getChatStatus() });
  const promptsQ = useQuery({ queryKey: ["chat", "prompts"], queryFn: () => ds.getChatPrompts() });
  const bar = { full, rich, listOpen, onClose: close };
  return (
    <aside
      aria-label="Chat"
      data-testid="spark-panel"
      data-size={full ? "full" : "panel"}
      className={cn(
        "spark-panel-in pointer-events-auto absolute inset-y-0 left-0 z-40 flex max-w-full border-r bg-card text-card-foreground shadow-[var(--shadow)]",
        full && "transition-[width] duration-200 motion-reduce:transition-none",
      )}
      style={{ width: chatPanelWidth(full, folded) }}
      onKeyDown={(e) => {
        // Escape anywhere in the panel closes it, and stops here: the graph's own Escape (selection, reader) waits
        if (e.key === "Escape" && !e.defaultPrevented) {
          e.stopPropagation();
          close();
        }
      }}
    >
      {status.isPending || promptsQ.isPending ? (
        <Column>
          <Header title="New chat" {...bar} />
          <div className="p-4">
            <Loading label="Loading chat" rows={3} />
          </div>
        </Column>
      ) : status.isError || promptsQ.isError ? (
        <Column>
          <Header title="New chat" {...bar} />
          <div className="p-4">
            <ErrorState title="The chat service is unreachable" error={status.error ?? promptsQ.error} onRetry={() => void Promise.all([status.refetch(), promptsQ.refetch()])} />
          </div>
        </Column>
      ) : (
        <Body status={status.data} prompts={promptsQ.data.prompts} scope={scope ?? ""} {...bar} server={ds.kind === "http" && !IS_SHARE} />
      )}
    </aside>
  );
}

const Column = ({ children }: { children: React.ReactNode }) => <div className="flex min-w-0 flex-1 flex-col">{children}</div>;

interface BarProps {
  /** the full chat (flag chat-full is on and the panel is grown) */
  full: boolean;
  /** flag chat-full: the size control, and in full the list and tools buttons */
  rich: boolean;
  listOpen: boolean;
  onClose: () => void;
  /** the tools sheet (plan, skills, prompts) in the full chat */
  tools?: { open: boolean; toggle: () => void; planning: boolean };
}

function Header({ title, full, rich, listOpen, onClose, tools }: BarProps & { title: string }) {
  const btn = "size-8";
  return (
    <header className="flex items-start gap-2 border-b px-5 py-3">
      {full && (
        <Button variant="ghost" size="icon" className={`${btn} -ml-3`} aria-label="Chat list" aria-pressed={listOpen} title={listOpen ? "Hide the chat list" : "Show the chat list"} onClick={() => useChatFull.getState().toggleList()}>
          <PanelLeft aria-hidden strokeWidth={1.6} />
        </Button>
      )}
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-[15px] font-semibold" data-testid="spark-title">
          {title}
        </h2>
        <p className="text-xs text-muted-foreground">knows the graph you are looking at</p>
      </div>
      {full && tools && (
        <Button variant="ghost" size="icon" className={`${btn} relative`} aria-label="Plan, skills and prompts" aria-expanded={tools.open} title="Plan, skills and prompts" onClick={tools.toggle}>
          <SlidersHorizontal aria-hidden strokeWidth={1.6} />
          {tools.planning && <span aria-hidden className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-primary" />}
        </Button>
      )}
      {rich && (
        <Button
          variant="ghost"
          size="icon"
          className={btn}
          aria-label={full ? "Back to the panel" : "Full screen"}
          title={full ? "Back to the panel" : "Full screen"}
          onClick={() => useChatFull.getState().setFull(!full)}
        >
          {full ? <Minimize2 aria-hidden strokeWidth={1.6} /> : <Maximize2 aria-hidden strokeWidth={1.6} />}
        </Button>
      )}
      <Button variant="ghost" size="icon" className={`${btn} -mr-2`} aria-label="Close chat" onClick={onClose}>
        <X aria-hidden strokeWidth={1.6} />
      </Button>
    </header>
  );
}

type Status = Parameters<typeof parseStatus>[0];
type Prompts = Parameters<typeof parsePrompts>[0];

function Body({ status, prompts, scope, full, rich, listOpen, onClose, server }: { status: Status; prompts: Prompts; scope: string; server: boolean } & BarProps) {
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
  const [toolsOpen, setToolsOpen] = useState(false);
  const model = view.models.some((m) => m.id === modelPick) ? modelPick : view.defaultModel;
  const options = () => ({ ...quickSendOptions(status, prompts), model, scope });
  const title = chat.messages.length ? chatTitle(chat.messages) : "New chat";
  const chip = backendLabel(view);

  useEffect(() => box.current?.focus(), []);

  // flag chat-full: a node clicked on the graph hands its page over; the explorer lists the pages the last answer cited
  const seen = useRef(useChatFull.getState().mention?.n ?? 0);
  useEffect(
    () =>
      useChatFull.subscribe((s) => {
        if (!rich || !s.mention || s.mention.n === seen.current) return;
        seen.current = s.mention.n;
        const id = s.mention.id;
        setText((t) => (t.split(/\s+/).includes(`@${id}`) ? t : `${t}${t && !/\s$/.test(t) ? " " : ""}@${id} `));
        box.current?.focus();
      }),
    [rich],
  );
  const cited = useMemo(() => {
    const hits = [...chat.messages].reverse().find((m) => m.role === "assistant" && m.hits)?.hits ?? [];
    return hits.flatMap((h) => (h.kind === "web" ? [] : [h.slug]));
  }, [chat.messages]);
  useEffect(() => {
    if (!rich) return;
    useChatFull.getState().setCited(cited);
    return () => useChatFull.getState().setCited([]);
  }, [rich, cited]);

  const planning = !!chat.todo?.some((t) => t.status !== "completed") && busy;
  const tools = full && rich ? { open: toolsOpen, toggle: () => setToolsOpen((o) => !o), planning } : undefined;

  return (
    <>
      {full && listOpen && (
        <div className="w-[var(--list-w)] shrink-0 border-r" style={{ "--list-w": `${FULL_LIST_W}px` } as React.CSSProperties}>
          <ChatList activeId={chat.id} server={server} />
        </div>
      )}
      <Column>
        <Header title={title} full={full} rich={rich} listOpen={listOpen} onClose={onClose} tools={tools} />
        {tools?.open && <ChatTools prompts={parsePrompts(prompts)} todo={chat.todo} busy={busy} sessionId={sessionIdOf(chat.id)} />}
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4 [&_li[data-testid=tool-line]]:w-fit [&_li[data-testid=tool-line]]:max-w-full [&_li[data-testid=tool-line]]:rounded-md [&_li[data-testid=tool-line]]:bg-secondary/60 [&_li[data-testid=tool-line]]:px-2 [&_li[data-testid=tool-line]]:py-0.5">
          {chat.messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">Ask about the pages on the graph. The agent searches and reads your wiki, read-only, and cites what it opened.</p>
          ) : (
            <MessageList messages={chat.messages} busy={busy} onRegenerate={() => regenerate(options())} onAnswer={answer} />
          )}
        </div>
        <div className="flex flex-col gap-2 px-4 pb-4 pt-2">
          <SparkComposer
            text={text}
            setText={setText}
            busy={busy}
            box={box}
            rich={rich}
            onStop={stop}
            onSend={(q) => {
              send(q, options());
              setText("");
            }}
          />
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
      </Column>
    </>
  );
}
