import { AlertCircle, Brain, Check, ChevronRight, FileText, FolderSearch, Globe, Loader2, Search, Terminal, Wrench, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ToolStep } from "./sse";
import type { ChatMessage } from "./thread";

/** The Claude-Code-style pieces of an assistant message (agent mode): thinking and tool lines (the todo list is `PlanPanel`). */

const TOOL_ICONS: Record<string, LucideIcon> = {
  Read: FileText,
  Grep: Search,
  Glob: FolderSearch,
  Bash: Terminal,
  WebSearch: Globe,
  WebFetch: Globe,
};

const chevron = <ChevronRight aria-hidden className="size-3.5 shrink-0 transition-transform group-open:rotate-90" />;

/** Collapsed by default; while the model is still thinking the summary says so. */
export function ThinkingBlock({ text, secs, live }: { text: string; secs?: number; live: boolean }) {
  const label = live && secs == null ? "Thinking…" : secs != null ? `Thought for ${secs}s` : "Thought";
  return (
    <details className="group mb-2 text-xs text-muted-foreground" data-testid="thinking">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 [&::-webkit-details-marker]:hidden">
        {chevron}
        <Brain aria-hidden className="size-3.5 shrink-0" />
        <span>{label}</span>
      </summary>
      <p className="mt-1 whitespace-pre-wrap break-words border-l pl-3 italic">{text}</p>
    </details>
  );
}

/** One tool call as a one-liner: icon, input summary, status; opens to the result preview. */
export function ToolLine({ step }: { step: ToolStep }) {
  const Icon = TOOL_ICONS[step.name] ?? Wrench;
  const failed = step.error || step.status === "error";
  const running = step.status === "running";
  const body = (chev: boolean) => (
    <>
      {chev ? chevron : <span className="size-3.5 shrink-0" />}
      <Icon aria-hidden className="size-3.5 shrink-0" />
      <span className="min-w-0 flex-1 truncate">
        <span className="font-medium">{step.name}</span> {step.summary}
      </span>
      {running && <Loader2 aria-label="running" className="size-3.5 shrink-0 animate-spin motion-reduce:animate-none" />}
      {failed && <AlertCircle aria-label="failed" className="size-3.5 shrink-0" />}
      {!running && !failed && step.status === "done" && <Check aria-hidden className="size-3.5 shrink-0 opacity-60" />}
    </>
  );
  const cls = cn("flex items-center gap-1.5", failed ? "text-bad" : "text-muted-foreground");
  if (!step.result) {
    return (
      <li className="text-xs" data-testid="tool-line">
        <div className={cls}>{body(false)}</div>
      </li>
    );
  }
  return (
    <li className="text-xs" data-testid="tool-line">
      <details className="group">
        <summary className={cn(cls, "cursor-pointer list-none [&::-webkit-details-marker]:hidden")}>{body(true)}</summary>
        <pre className={cn("mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-secondary/50 p-2 font-mono text-[11px]", failed ? "text-bad" : "text-muted-foreground")}>
          {step.result}
        </pre>
      </details>
    </li>
  );
}

export function ToolLines({ steps }: { steps: ToolStep[] }) {
  if (!steps.length) return null;
  return (
    <ul className="mb-2 flex flex-col gap-1" aria-label="Tool calls">
      {steps.map((s, i) => (
        <ToolLine key={s.id ?? i} step={s} />
      ))}
    </ul>
  );
}

/** Thinking and tool lines of one assistant message. */
export function Transcript({ message, live }: { message: ChatMessage; live: boolean }) {
  return (
    <>
      {message.thinking && <ThinkingBlock text={message.thinking} secs={message.thinkSecs} live={live} />}
      {message.trace && <ToolLines steps={message.trace} />}
    </>
  );
}
