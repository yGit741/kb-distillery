import { useQuery } from "@tanstack/react-query";
import { PanelLeft, SlidersHorizontal, X } from "lucide-react";
import { useChatDock } from "../tools/chatDockStore";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { useDataSource } from "@/api";
import { useFlag } from "@/flags/useFlag";
import { capabilities } from "./capabilities";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ComposerLine } from "@/features/chat/ComposerLine";
import { cn } from "@/lib/utils";
import { MessageList } from "@/features/chat/MessageList";
import { NeedsClaudeBadge } from "@/features/chat/NeedsClaudeBadge";
import { parsePrompts } from "@/features/chat/prompts";
import { quickSendOptions } from "@/features/chat/QuickAsk";
import { STATUS_KEY } from "@/features/chat/SessionPanel";
import { backendLabel, effectiveBackend, parseStatus } from "@/features/chat/status";
import { readJson, writeJson } from "@/features/chat/storage";
import { chatTitle, type ChatMessage } from "@/features/chat/thread";
import { useChatSession } from "@/features/chat/useChatSession";
import { sessionIdOf } from "@/features/chat/serverStorage";
import { ReplayControl, ReplaySteps } from "./AnswerReplay";
import { ShowThinking } from "./ShowThinking";
import { rolesOf, thinkingOf } from "./thinking";
import { useThinking } from "./thinkingStore";
import { useLabHud } from "../lab/hud";
import type { CiteHooks } from "@/components/Markdown";
import { ChatList } from "./ChatList";
import { ChatTools } from "./ChatTools";
import { CitesButton } from "./CitesButton";
import { PANEL_MAX_W, PANEL_MIN_W, useChatFull } from "./chatFullStore";
import { chatPanelWidth } from "./layout";
import { DragEdge } from "./DragEdge";
import { SparkComposer } from "./SparkComposer";
import { citedSlugs, slugOfHref } from "./cites";
import { useCites } from "./citeStore";
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
  const panelW = useChatFull((s) => s.panelW);
  const paneW = useChatFull((s) => s.paneW);
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
      style={{ width: chatPanelWidth(full, folded, panelW, paneW) }}
      onKeyDown={(e) => {
        // Escape anywhere in the panel stops here (the graph's own Escape waits): the first one puts out the glow of
        // the cited pages on the graph, the next one closes the panel
        if (e.key === "Escape" && !e.defaultPrevented) {
          e.stopPropagation();
          if (!clearGlow()) close();
        }
      }}
    >
      {!full && <ResizeEdge width={panelW} />}
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
        <Body status={status.data} prompts={promptsQ.data.prompts} scope={scope ?? ""} {...bar} server={ds.kind === "http" && capabilities().chat} />
      )}
    </aside>
  );
}

/** Puts out the graph glow of the answer on screen (cited pages, the thinking view); true when there was one. */
function clearGlow(): boolean {
  const lit = useCites.getState().slugs.length > 0 || useThinking.getState().view !== null;
  if (!lit) return false;
  useCites.getState().clear();
  useThinking.getState().dismiss();
  return true;
}

/** The panel's right edge: drag it to widen or narrow the panel; arrow keys step it. */
function ResizeEdge({ width }: { width: number }) {
  const set = useChatFull.getState().setPanelW;
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the chat panel"
      aria-valuenow={width}
      aria-valuemin={PANEL_MIN_W}
      aria-valuemax={PANEL_MAX_W}
      tabIndex={0}
      data-testid="spark-resize"
      className="absolute inset-y-0 -right-1 z-10 w-2 cursor-col-resize after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:bg-transparent hover:after:bg-ring focus-visible:outline-none focus-visible:after:bg-ring"
      onPointerDown={(e) => {
        e.preventDefault();
        const x0 = e.clientX;
        const w0 = width;
        const move = (ev: PointerEvent) => set(w0 + ev.clientX - x0);
        const up = () => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          window.removeEventListener("pointercancel", up);
          document.body.style.cursor = "";
        };
        document.body.style.cursor = "col-resize";
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
        window.addEventListener("pointercancel", up);
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") set(width - 24);
        else if (e.key === "ArrowRight") set(width + 24);
      }}
    />
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
  const listW = useChatFull((s) => s.listW);
  return (
    <header className="flex items-start gap-2 border-b px-5 py-3">
      {/* close and size sit at the left and never move: in full the list opens under them and the title moves right */}
      <div className="flex shrink-0 items-start gap-2" style={full && listOpen ? { width: listW - 20 } : undefined}>
        <Button variant="ghost" size="icon" className={`${btn} -ml-3`} aria-label="Close chat" onClick={onClose}>
          <X aria-hidden strokeWidth={1.6} />
        </Button>
        {/* the tools sit between close and the book, in both sizes, so the book never moves */}
        {rich && (
          <Button
            variant="ghost"
            size="icon"
            className={`${btn} relative`}
            aria-label="Plan, skills and prompts"
            aria-expanded={tools?.open ?? false}
            title="Plan, skills and prompts"
            disabled={!tools}
            onClick={tools?.toggle}
          >
            <SlidersHorizontal aria-hidden strokeWidth={1.6} />
            {tools?.planning && <span aria-hidden className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-primary" />}
          </Button>
        )}
        {rich && (
          <Button
            variant="ghost"
            size="icon"
            className={btn}
            aria-label={full ? "Back to the panel" : "Full screen"}
            aria-pressed={full}
            title={full ? "Back to the panel" : "Full screen"}
            onClick={() => {
              const s = useChatFull.getState();
              if (!full && !listOpen) s.toggleList();
              s.setFull(!full);
            }}
          >
            <PanelLeft aria-hidden strokeWidth={1.6} />
          </Button>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-[15px] font-semibold" data-testid="spark-title">
          {title}
        </h2>
        <p className="text-xs text-muted-foreground">knows the graph you are looking at</p>
      </div>
    </header>
  );
}

/**
 * The pages the answer on screen cites, lit on the graph (./citeStore). The answer on screen is the newest one until the
 * reader scrolls another into the middle. The graph frames the cited pages once when an answer finishes or the chat
 * opens, never on a render; a click on a lit page scrolls here to the sentence that cites it.
 */
function useCitedPages(scroller: RefObject<HTMLDivElement | null>, messages: ChatMessage[], busy: boolean, still = false) {
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

  // frame the cited pages when an answer finishes (busy to idle) and once when a chat opens with one: never on send or scroll
  const wasBusy = useRef(busy);
  const opened = useRef(false);
  useEffect(() => {
    const finished = wasBusy.current && !busy;
    wasBusy.current = busy;
    const first = !opened.current;
    opened.current = true;
    // flag show-thinking: nothing moves, the camera included
    if (!slugs.length || busy || still) return;
    if ((finished && idx === lastAssistant) || (first && !finished)) useCites.getState().refit();
  }, [busy, slugs, idx, lastAssistant, still]);

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
  const idxRef = useRef(idx);
  idxRef.current = idx;
  useEffect(() => {
    const el = scroller.current;
    if (!req || !el) return;
    useCites.setState({ scrollReq: null }); // consumed: a later answer, scroll or reopening never replays it
    const li = el.querySelectorAll<HTMLElement>("li[data-role]")[idxRef.current];
    const link = [...(li?.querySelectorAll<HTMLAnchorElement>("a") ?? [])].find((a) => slugOfHref(a.getAttribute("href")) === req.slug);
    const line = link?.closest<HTMLElement>("p, li") ?? link;
    if (!line) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    line.scrollIntoView?.({ block: "center", behavior: still ? "auto" : "smooth" });
    line.setAttribute("data-cited-now", "");
    const t = window.setTimeout(() => line.removeAttribute("data-cited-now"), 1800);
    return () => window.clearTimeout(t);
  }, [req, scroller]);

  return { slugs, idx };
}

type Status = Parameters<typeof parseStatus>[0];
type Prompts = Parameters<typeof parsePrompts>[0];

function Body({ status, prompts, scope, full, rich, listOpen, onClose, server }: { status: Status; prompts: Prompts; scope: string; server: boolean } & BarProps) {
  const listW = useChatFull((s) => s.listW);
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
  const scroller = useRef<HTMLDivElement>(null);
  const thinkingFlag = useFlag("show-thinking");
  const sparkFlag = useFlag("spark-chat");
  const thinkingOn = thinkingFlag && sparkFlag;
  const { slugs: cited, idx: onScreen } = useCitedPages(scroller, chat.messages, busy, thinkingOn);
  useThinkingGraph(thinkingOn, chat.messages, onScreen, busy);
  const citeHooks = useCiteHooks(thinkingOn, onScreen);
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
  useEffect(() => {
    if (!rich) return;
    useChatFull.getState().setCited(cited);
    return () => useChatFull.getState().setCited([]);
  }, [rich, cited]);

  // an answer on the way: the list and the deep link refuse to remount the panel under it
  useEffect(() => {
    useChatFull.getState().setBusy(busy);
    return () => useChatFull.getState().setBusy(false);
  }, [busy]);
  // text handed in without a remount (a question from /chat?q= while the panel is open)
  const seenInsert = useRef(useChatFull.getState().insert?.n ?? 0);
  useEffect(
    () =>
      useChatFull.subscribe((s) => {
        if (!s.insert || s.insert.n === seenInsert.current) return;
        seenInsert.current = s.insert.n;
        const q = s.insert.text;
        setText((t) => (t.trim() ? `${t.trimEnd()} ${q}` : q));
        box.current?.focus();
      }),
    [],
  );
  const notice = useChatFull((s) => s.notice);
  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => useChatFull.getState().setNotice(""), 8000);
    return () => window.clearTimeout(t);
  }, [notice]);

  const planning = !!chat.todo?.some((t) => t.status !== "completed") && busy;
  const tools = rich ? { open: toolsOpen, toggle: () => setToolsOpen((o) => !o), planning } : undefined;

  return (
    <>
      <Column>
        <Header title={title} full={full} rich={rich} listOpen={listOpen} onClose={onClose} tools={tools} />
        <div className="flex min-h-0 flex-1">
          {full && listOpen && (
            <div className="relative w-[var(--list-w)] shrink-0 border-r" style={{ "--list-w": `${listW}px` } as React.CSSProperties}>
              <ChatList activeId={chat.id} server={server} />
              <DragEdge label="Resize the chat list" axis="x" testId="list-resize" start={listW} onDrag={(d, w0) => useChatFull.getState().setListW(w0 + d)} />
            </div>
          )}
          <Column>
        {notice && (
          <p role="status" data-testid="chat-notice" className="border-b px-5 py-2 text-xs text-muted-foreground">
            {notice}
          </p>
        )}
        {!view.claudeAvailable && (
          <p role="status" data-testid="chat-needs-claude" className="flex flex-wrap items-center gap-2 border-b px-5 py-2 text-xs text-muted-foreground">
            <NeedsClaudeBadge reason={view.claudeReason} />
            {view.claudeReason}
          </p>
        )}
        {tools?.open && <ChatTools prompts={parsePrompts(prompts)} todo={chat.todo} busy={busy} sessionId={sessionIdOf(chat.id)} />}
        <div ref={scroller} className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4 [&_[data-cited-now]]:rounded-sm [&_[data-cited-now]]:bg-primary/10 [&_[data-cited-now]]:transition-colors [&_li[data-testid=tool-line]]:w-fit [&_li[data-testid=tool-line]]:max-w-full [&_li[data-testid=tool-line]]:rounded-md [&_li[data-testid=tool-line]]:bg-secondary/60 [&_li[data-testid=tool-line]]:px-2 [&_li[data-testid=tool-line]]:py-0.5">
          {chat.messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">Ask about the pages on the graph. The agent searches and reads your wiki, read-only, and cites what it opened.</p>
          ) : (
            <MessageList
              messages={chat.messages}
              busy={busy}
              onRegenerate={() => regenerate(options())}
              onAnswer={answer}
              actions={(m, i) =>
                m.role === "assistant" ? (
                  <>
                    <CitesButton message={m} />
                    {!thinkingOn && <ReplayControl message={m} index={i} />}
                  </>
                ) : null
              }
              below={thinkingOn ? undefined : (m, i) => (m.role === "assistant" ? <ReplaySteps message={m} index={i} /> : null)}
              thinking={thinkingOn ? (m, _i, streaming) => <ShowThinking message={m} streaming={streaming} /> : undefined}
              cite={citeHooks}
            />
          )}
        </div>
        {!thinkingOn && cited.length > 0 && (
          <p className="px-5 pb-1 text-xs text-muted-foreground" data-testid="spark-cites">
            {cited.length} cited page{cited.length === 1 ? "" : "s"} lit on the graph
          </p>
        )}
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
        </div>
      </Column>
    </>
  );
}

/**
 * Flag show-thinking: the answer on screen puts what it looked at on the graph (./thinkingStore), from the first tool
 * call onward, until the reader dismisses it; the next message brings it back.
 */
function useThinkingGraph(on: boolean, messages: ChatMessage[], idx: number, busy: boolean) {
  const m = idx >= 0 ? messages[idx] : undefined;
  const streaming = busy && idx === messages.length - 1;
  const dismissed = useThinking((s) => s.dismissed);
  // keyed on the trace and the finished text, not the message object: a streamed token changes neither
  const trace = m?.role === "assistant" ? m.trace : undefined;
  const text = streaming ? "" : (m?.content ?? "");
  const view = useMemo(() => {
    if (!on || !trace?.length) return null;
    const t = thinkingOf(trace, text);
    return { msg: idx, roles: rolesOf(t, !streaming), citeNo: t.citeNo, web: t.webSources };
  }, [on, trace, text, idx, streaming]);
  useEffect(() => {
    useThinking.getState().set(view && view.msg !== dismissed ? view : null);
  }, [view, dismissed]);
  // a new message, or a regenerated answer (same count, a new run), reopens the view
  const count = messages.length;
  useEffect(() => {
    useThinking.getState().undismiss();
  }, [count]);
  useEffect(() => {
    if (busy) useThinking.getState().undismiss();
  }, [busy]);
  useEffect(() => () => useThinking.getState().clear(), []);
}

/** Numbered citations in every answer; the one on screen also links its words and its nodes both ways. */
function useCiteHooks(on: boolean, idx: number): ((m: ChatMessage, i: number) => CiteHooks | undefined) | undefined {
  // flag off: no subscription, so a graph hover never re-renders the chat
  const hot = useThinking((s) => (on ? s.hot : null));
  const graphHover = useLabHud((s) => (on ? s.hover : null));
  return useMemo(() => {
    if (!on) return undefined;
    const onHot = (slug: string | null) => useThinking.getState().setHot(slug);
    return (m: ChatMessage, i: number) => {
      if (m.role !== "assistant") return undefined;
      const map = new Map(citedSlugs(m.content).map((s, n) => [s, n + 1] as const));
      return { numberOf: (s: string) => map.get(s), hot: i === idx ? (hot ?? graphHover) : null, onHot: i === idx ? onHot : undefined };
    };
  }, [on, idx, hot, graphHover]);
}
