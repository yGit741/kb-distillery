import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Compass,
  FileText,
  Flag,
  Folder,
  Globe,
  List,
  Network,
  Paperclip,
  Search,
  Tag,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type { ToolStep } from "@/features/chat/sse";
import type { ChatMessage } from "@/features/chat/thread";
import { NodeSwatch } from "../encoding/NodeMarkSvg";
import { useChatFull } from "./chatFullStore";
import { useReplay } from "./replayStore";
import { hostOf, isWeb, KIND_LABEL, kindOf, liveStatus, resultOf, summaryOf, thinkingOf, type Kind, type Thinking } from "./thinking";
import { useThinking } from "./thinkingStore";

/** One line icon per kind of call (lucide, 1.6). The magnifier is keyword search only; the web is a globe. */
const ICON: Record<Kind, LucideIcon> = {
  shortlist: List,
  meaning: Compass,
  graph: Network,
  raw: FileText,
  alias: Tag,
  keyword: Search,
  files: Folder,
  open: BookOpen,
  attachment: Paperclip,
  "web-search": Globe,
  "web-source": Globe,
  other: Wrench,
};

const Dots = () => (
  <span aria-hidden className="inline-flex gap-0.5 [&>i]:size-1 [&>i]:rounded-full [&>i]:bg-muted-foreground [&>i]:motion-safe:animate-pulse">
    <i />
    <i className="[animation-delay:200ms]" />
    <i className="[animation-delay:400ms]" />
  </span>
);

function usePageInfo() {
  const pages = useChatFull((s) => s.pages);
  const byId = useThinking((s) => s.byId);
  return (slug: string) => {
    const n = byId?.get(slug);
    return { title: n?.title || pages.find((p) => p.id === slug)?.title || slug, type: n?.type };
  };
}

/** What the call was about, in the agent's own words. */
function whatOf(t: ToolStep, title: (s: string) => string): string {
  const k = kindOf(t);
  if (k === "web-source") return hostOf(t.url) || t.summary;
  if (t.query) return t.query;
  if (k === "open" && t.read?.length) return t.read.map(title).join(", ");
  return t.summary;
}

function Chip({ slug, missable }: { slug: string; missable: boolean }) {
  const info = usePageInfo()(slug);
  const missed = useReplay((s) => s.missed.includes(slug));
  const body = (
    <>
      {info.type && <NodeSwatch type={info.type} className="size-3" />}
      <span className="max-w-48 truncate">{info.title}</span>
    </>
  );
  const base = "inline-flex min-h-6 items-center gap-1 rounded-md border px-1.5 text-[11.5px]";
  if (!missable) return <li className={cn(base, "text-muted-foreground")}>{body}</li>;
  return (
    <li>
      <button
        type="button"
        aria-pressed={missed}
        title={missed ? "Marked as missed: rides on your next message" : "Mark as missed: the agent should have read it"}
        className={cn(base, "hover:bg-secondary", missed ? "border-foreground text-foreground" : "text-muted-foreground")}
        onClick={() => useReplay.getState().toggleMissed(slug)}
      >
        {body}
      </button>
    </li>
  );
}

function Call({ t, done, missable }: { t: ToolStep; done: boolean; missable: ReadonlySet<string> }) {
  const k = kindOf(t);
  const Icon = ICON[k];
  const web = isWeb(k);
  const res = resultOf(t);
  const label = k === "web-source" ? "web source" : KIND_LABEL[k];
  return (
    <li data-testid="thinking-call" data-kind={k} className={cn("flex flex-col", web && "-mx-1.5 rounded-md bg-secondary/70 px-1.5 py-0.5")}>
      <div className="grid grid-cols-[16px_1fr_auto] items-start gap-1.5 text-[13px]">
        <Icon aria-hidden strokeWidth={1.6} className="mt-[3px] size-3.5 text-muted-foreground" data-icon={web ? "globe" : k === "keyword" ? "search" : k} />
        <span className="min-w-0 break-words">
          {web && (
            <span data-testid="web-badge" className="mr-1.5 inline-block rounded border px-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              Web
            </span>
          )}
          <span className={cn(t.query && k !== "web-source" && "rounded bg-secondary px-1 font-mono text-[11.5px]")}>{whatOf(t, pageTitle)}</span>
          {label && <span className="ml-1.5 text-xs text-muted-foreground">{label}</span>}
        </span>
        <span className={cn("whitespace-nowrap text-[12.5px]", res ? (res === "failed" ? "text-bad" : "text-foreground") : "text-muted-foreground")}>{res ?? <Dots />}</span>
      </div>
      {k === "web-search" && !!t.domains?.length && (
        <ul aria-label="Result sites" className="mb-0.5 ml-[22px] mt-1 flex flex-wrap gap-1">
          {t.domains.map((d) => (
            <li key={d} className="rounded border bg-card px-1.5 text-[11.5px] text-muted-foreground">
              {d}
            </li>
          ))}
        </ul>
      )}
      {!web && !!t.seen?.length && (
        <ul aria-label="Pages found" className="mb-0.5 ml-[22px] mt-1 flex flex-wrap gap-1">
          {t.seen.map((s) => (
            <Chip key={s} slug={s} missable={done && missable.has(s)} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** Title lookup outside a component's hooks (the store is read directly; chips subscribe themselves). */
function pageTitle(slug: string): string {
  const n = useThinking.getState().byId?.get(slug);
  return n?.title || useChatFull.getState().pages.find((p) => p.id === slug)?.title || slug;
}

function Rounds({ t, done }: { t: Thinking; done: boolean }) {
  const missable = useMemo(() => new Set(t.missable), [t.missable]);
  return (
    <ol aria-label="Rounds" className="flex flex-col">
      {t.rounds.map((r) => (
        <li key={r.n} data-testid="thinking-round" className="border-b border-border/60 py-1.5 last:border-b-0">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Round {r.n}
            {r.steps.length > 1 ? ` · ${r.steps.length} at once` : ""}
          </p>
          <ul className="mt-0.5 flex flex-col gap-0.5">
            {r.steps.map((s, i) => (
              <Call key={s.id ?? i} t={s} done={done} missable={missable} />
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

function Cited({ t }: { t: Thinking }) {
  const info = usePageInfo();
  const bad = useReplay((s) => s.bad);
  if (!t.citeNo.size) return null;
  return (
    <div data-testid="thinking-cited" className="border-t border-border/60 py-1.5">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Cited in the answer</p>
      <ul className="mt-0.5 flex flex-col">
        {[...t.citeNo].map(([slug, n]) => {
          const isBad = bad.includes(slug);
          return (
            <li key={slug} className="flex min-h-7 items-center gap-2 text-[13px]" onMouseEnter={() => useThinking.getState().setHot(slug)} onMouseLeave={() => useThinking.getState().setHot(null)}>
              <span className="grid size-[18px] shrink-0 place-items-center rounded-full bg-foreground text-[10px] font-semibold text-background">{n}</span>
              <span className={cn("min-w-0 flex-1 truncate", isBad && "line-through decoration-muted-foreground")}>{info(slug).title}</span>
              <button
                type="button"
                aria-pressed={isBad}
                aria-label={isBad ? `Remove the bad citation mark on ${info(slug).title}` : `Mark ${info(slug).title} as a bad citation`}
                title={isBad ? "Remove the bad citation mark" : "Mark as a bad citation"}
                className={cn("grid size-6 shrink-0 place-items-center rounded-md hover:bg-secondary", isBad ? "text-foreground" : "text-muted-foreground")}
                onClick={() => useReplay.getState().toggleBad(slug)}
              >
                <Flag aria-hidden strokeWidth={1.6} className="size-3.5" fill={isBad ? "currentColor" : "none"} />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function OpenedNotCited({ t }: { t: Thinking }) {
  const info = usePageInfo();
  if (!t.openedNotCited.length) return null;
  return (
    <div data-testid="thinking-not-cited" className="border-t border-border/60 py-1.5">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Opened, not cited</p>
      <p className="text-[13px]">{t.openedNotCited.map((s) => info(s).title).join(" · ")}</p>
    </div>
  );
}

/**
 * "Show my thinking" under an answer (flag `show-thinking`), folded by default. Folded: one header with the counts,
 * and while the answer streams one live word. Unfolded: the rounds of calls, then the citations and the pages
 * opened but not named. Found pages not opened are chips to mark as missed; a citation's flag marks it as bad.
 */
export function ShowThinking({ message, streaming }: { message: ChatMessage; streaming: boolean }) {
  const [open, setOpen] = useState(false);
  const t = useMemo(() => thinkingOf(message.trace, streaming ? "" : message.content), [message.trace, message.content, streaming]);
  const missed = useReplay((s) => s.missed);
  const bad = useReplay((s) => s.bad);
  if (!message.trace?.length && !streaming) return null;
  const done = !streaming;
  const live = liveStatus(message.trace, message.content);
  return (
    <section data-testid="show-thinking" aria-label="Show my thinking" className="mt-2 border-t border-border/60 pt-1">
      <button
        type="button"
        aria-expanded={open}
        className="flex min-h-7 w-full items-center justify-between gap-2 text-left text-[12.5px] text-muted-foreground hover:text-foreground"
        onClick={() => {
          setOpen((o) => !o);
          useThinking.getState().undismiss();
        }}
      >
        <span className="flex items-center gap-1.5">
          {open ? <ChevronDown aria-hidden strokeWidth={1.6} className="size-3.5" /> : <ChevronRight aria-hidden strokeWidth={1.6} className="size-3.5" />}
          Show my thinking
        </span>
        <span data-testid="thinking-summary" className="tabular-nums">
          {summaryOf(t)}
          {streaming ? " so far" : ""}
        </span>
      </button>
      {streaming && (
        <p role="status" data-testid="thinking-live" className="flex min-h-6 items-center gap-1.5 text-[12.5px] text-muted-foreground">
          <Dots /> {live}
        </p>
      )}
      {open && (
        <div data-testid="thinking-body" className="pb-1">
          <Rounds t={t} done={done} />
          {done && (
            <>
              {t.missable.length > 0 && <p className="pt-1 text-xs text-muted-foreground">Found but not opened: click a page to mark it as missed.</p>}
              <Cited t={t} />
              <OpenedNotCited t={t} />
              {(missed.length > 0 || bad.length > 0) && <p className="pt-1 text-xs text-muted-foreground">Marks ride on your next message.</p>}
            </>
          )}
        </div>
      )}
    </section>
  );
}
