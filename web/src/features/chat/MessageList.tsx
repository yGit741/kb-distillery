import { Link } from "@tanstack/react-router";
import { Globe, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";
import { useFlag } from "@/flags/useFlag";
import { cn } from "@/lib/utils";
import { tokenLine } from "./format";
import type { AskQuestion, ToolStep } from "./sse";
import type { ChatMessage } from "./thread";
import { Transcript } from "./Transcript";

function Trace({ steps, live }: { steps: ToolStep[]; live: boolean }) {
  if (!steps.length) return null;
  const last = steps[steps.length - 1]!;
  if (live) {
    return (
      <p className="mb-1 text-xs text-muted-foreground" role="status">
        {last.name.toLowerCase()}: {last.summary}
      </p>
    );
  }
  const reads = steps.filter((t) => t.name === "Read" && /^read /.test(t.summary)).length;
  return (
    <details className="mb-1 text-xs text-muted-foreground">
      <summary className="cursor-pointer">
        {steps.length} step{steps.length === 1 ? "" : "s"} · {reads} page{reads === 1 ? "" : "s"} read
      </summary>
      <ol className="mt-1 list-decimal space-y-0.5 pl-5">
        {steps.map((t, i) => (
          <li key={t.id ?? i} className={t.error ? "text-bad" : undefined}>
            <span className="font-medium">{t.name}</span> {t.summary}
          </li>
        ))}
      </ol>
    </details>
  );
}

/** The agent's question: one button per option. A single plain question answers on click; otherwise pick, then send. */
export function AskCard({ ask, onAnswer }: { ask: { id: string; questions: AskQuestion[] }; onAnswer: (id: string, answers: Record<string, string>) => void }) {
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const instant = ask.questions.length === 1 && !ask.questions[0]!.multiSelect;
  const toggle = (q: AskQuestion, label: string) => {
    if (instant) return onAnswer(ask.id, { [q.question]: label });
    setPicked((p) => {
      const cur = p[q.question] ?? [];
      const next = q.multiSelect ? (cur.includes(label) ? cur.filter((l) => l !== label) : [...cur, label]) : [label];
      return { ...p, [q.question]: next };
    });
  };
  const ready = ask.questions.every((q) => (picked[q.question]?.length ?? 0) > 0);
  return (
    <div role="group" aria-label="The agent asks" className="mt-2 flex flex-col gap-3 rounded-md border bg-secondary/30 p-3">
      {ask.questions.map((q) => (
        <div key={q.question} className="flex flex-col gap-1.5">
          <p className="text-sm font-medium">{q.question}</p>
          <div className="flex flex-wrap gap-2">
            {q.options.map((o) => (
              <Button
                key={o.label}
                size="sm"
                variant={picked[q.question]?.includes(o.label) ? "default" : "outline"}
                title={o.description}
                aria-pressed={instant ? undefined : picked[q.question]?.includes(o.label) ?? false}
                onClick={() => toggle(q, o.label)}
              >
                {o.label}
              </Button>
            ))}
          </div>
        </div>
      ))}
      {!instant && (
        <Button
          size="sm"
          className="self-start"
          disabled={!ready}
          onClick={() => onAnswer(ask.id, Object.fromEntries(ask.questions.map((q) => [q.question, (picked[q.question] ?? []).join(", ")])))}
        >
          Send answers
        </Button>
      )}
    </div>
  );
}

interface Props {
  messages: ChatMessage[];
  busy: boolean;
  onRegenerate: () => void;
  onAnswer: (id: string, answers: Record<string, string>) => void;
}

export function MessageList({ messages, busy, onRegenerate, onAnswer }: Props) {
  const agentMode = useFlag("agent-mode");
  const end = useRef<HTMLDivElement>(null);
  const size = messages.length ? messages[messages.length - 1]!.content.length : 0;
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, size]);

  return (
    <ol className="flex flex-col gap-4" aria-live="polite" aria-label="Conversation">
      {messages.map((m, i) => {
        const isLast = i === messages.length - 1;
        const streaming = busy && isLast && m.role === "assistant";
        const user = m.role === "user";
        return (
          <li
            key={i}
            data-role={m.role}
            className={cn("rounded-lg border p-3", user ? "bg-secondary/50" : "bg-card", m.failed && "opacity-70")}
          >
            <p className="mb-1 text-xs font-medium text-muted-foreground">{user ? "You" : "Claude"}</p>
            {!user && (agentMode ? <Transcript message={m} live={streaming} /> : m.trace && <Trace steps={m.trace} live={streaming} />)}
            {user ? (
              <p className="whitespace-pre-wrap break-words text-sm">{m.content}</p>
            ) : m.content ? (
              <Markdown>{m.content}</Markdown>
            ) : streaming ? (
              <p className="text-sm text-muted-foreground">Thinking…</p>
            ) : null}
            {!user && m.ask && streaming && <AskCard ask={m.ask} onAnswer={onAnswer} />}
            {!user && m.meta && <p className="mt-2 text-xs text-muted-foreground">{m.meta}</p>}
            {!user && m.usage && <p className="text-xs text-muted-foreground">{tokenLine(m.usage)}</p>}
            {!user && m.error && (
              <p role="alert" className="mt-2 break-words text-xs text-bad">
                {m.error}
              </p>
            )}
            {!user && isLast && !busy && (
              <Button variant="ghost" size="sm" className="mt-2 -ml-2" onClick={onRegenerate}>
                <RefreshCw aria-hidden /> Regenerate
              </Button>
            )}
          </li>
        );
      })}
      <div ref={end} />
    </ol>
  );
}

export function Sources({ messages }: { messages: ChatMessage[] }) {
  const hits = [...messages].reverse().find((m) => m.role === "assistant" && m.hits)?.hits;
  if (!hits) return <p className="text-sm text-muted-foreground">Ask something to see which pages were used.</p>;
  if (!hits.length) {
    return <p className="text-sm text-muted-foreground">No matching pages. The answer relies on earlier context or general knowledge.</p>;
  }
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {hits.map((h) => h.kind === "web" ? (
        <li key={h.url} className="min-w-0">
          <a href={h.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-1 break-words text-primary underline-offset-2 hover:underline">
            <Globe aria-hidden className="mt-0.5 size-3.5 shrink-0" />
            {h.title || h.url}
          </a>
        </li>
      ) : (
        <li key={h.slug} className="min-w-0">
          <Link to={`/pages/${encodeURIComponent(h.slug)}` as "/"} className="break-words text-primary underline-offset-2 hover:underline">
            {h.slug}
          </Link>{" "}
          <span className="text-xs text-muted-foreground" title="Agent: times the page was read. Direct: retrieval score.">
            {h.score}
            {h.in_context ? " · already in context" : ""}
          </span>
          {h.summary && <p className="line-clamp-2 text-xs text-muted-foreground">{h.summary}</p>}
        </li>
      ))}
    </ul>
  );
}
