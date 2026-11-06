import { History } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { useFlag } from "@/flags/useFlag";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/features/chat/thread";
import { citedSlugs } from "./cites";
import { useChatFull } from "./chatFullStore";
import { replaySteps, viewAt } from "./replay";
import { useReplay } from "./replayStore";

/** Everything the control and the step list of one answer share (flag `spark-chat`). */
function useAnswerReplay(message: ChatMessage, index: number) {
  const on = useFlag("spark-chat");
  const steps = useMemo(() => replaySteps(message.trace), [message.trace]);
  const cited = useMemo(() => citedSlugs(message.content), [message.content]);
  const openMsg = useReplay((s) => s.msg);
  const step = useReplay((s) => s.step);
  const available = on && steps.length > 0;
  const isOpen = available && openMsg === index;
  const go = useCallback(
    (i: number) => {
      const n = Math.max(0, Math.min(i, steps.length - 1));
      useReplay.getState().show(n, viewAt(steps, n, cited));
    },
    [steps, cited],
  );
  const toggle = () => {
    if (isOpen) return useReplay.getState().close();
    const last = steps.length - 1;
    useReplay.getState().open(index, last, viewAt(steps, last, cited));
  };
  // the answer is gone (chat switched, panel closed) or the flag went off: the replay goes with it
  useEffect(() => {
    if (!available && useReplay.getState().msg === index) useReplay.getState().close();
  }, [available, index]);
  useEffect(
    () => () => {
      if (useReplay.getState().msg === index) useReplay.getState().close();
    },
    [index],
  );
  return { available, isOpen, steps, step, go, toggle, cited };
}

/** The small control under a past answer whose trace says which pages were seen and read. */
export function ReplayControl({ message, index }: { message: ChatMessage; index: number }) {
  const r = useAnswerReplay(message, index);
  if (!r.available) return null;
  return (
    <Button variant="ghost" size="sm" aria-pressed={r.isOpen} title="How this answer was built" aria-label="How this answer was built" data-testid="replay-control" onClick={r.toggle}>
      <History aria-hidden strokeWidth={1.6} /> How it was built
    </Button>
  );
}

/** The summary without its leading verb, which the bold name already says ("Read read x"). */
const plain = (t: { name: string; summary: string }) => (t.summary.toLowerCase().startsWith(`${t.name.toLowerCase()} `) ? t.summary.slice(t.name.length + 1) : t.summary);

const typing = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

/** The steps under the answer: click one, or press the left and right arrows, to scrub; Escape closes. */
export function ReplaySteps({ message, index }: { message: ChatMessage; index: number }) {
  const r = useAnswerReplay(message, index);
  const pages = useChatFull((s) => s.pages);
  const title = (slug: string) => pages.find((p) => p.id === slug)?.title || slug;
  const picked = useReplay((s) => s.picked);
  const bad = useReplay((s) => s.bad);
  const missed = useReplay((s) => s.missed);
  const candidates = useReplay((s) => s.candidates);
  const view = useReplay((s) => s.view);
  const { isOpen, go, step, steps } = r;

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // an open @page list closes first
        if (document.querySelector('[data-testid="mention-list"], [role="menu"], [role="dialog"]')) return;
        const t = e.target;
        if (t instanceof HTMLTextAreaElement && t.value) return; // a typed message keeps its own Escape
        e.preventDefault();
        e.stopPropagation(); // the panel's and the graph's own Escape wait: this one closes the replay only
        useReplay.getState().close();
      } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !typing(e.target) && !e.altKey && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        go(step + (e.key === "ArrowRight" ? 1 : -1));
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [isOpen, go, step]);

  if (!isOpen || !view) return null;
  const atEnd = view.atEnd;
  const pickedRole = picked ? view.roles.get(picked) : undefined;
  return (
    <div data-testid="replay-steps" className="mt-2 flex flex-col gap-1.5 border-t pt-2">
      <p className="text-xs text-muted-foreground">
        Step {step + 1} of {steps.length}. Left and right arrows step, Esc closes.
      </p>
      <ol aria-label="Steps of this answer" className="flex flex-col gap-0.5">
        {steps.map((t, i) => (
          <li key={t.id ?? i}>
            <button
              type="button"
              aria-current={i === step ? "step" : undefined}
              onClick={() => go(i)}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs",
                i === step ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60",
                i > step && "opacity-60",
              )}
            >
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">{t.name}</span> {plain(t)}
              </span>
              <span className="shrink-0 tabular-nums">{[t.seen?.length ? `${t.seen.length} seen` : "", t.read?.length ? `${t.read.length} read` : ""].filter(Boolean).join(", ")}</span>
            </button>
          </li>
        ))}
      </ol>
      {atEnd && (
        <div className="flex flex-col gap-1.5 text-xs text-muted-foreground" data-testid="replay-marks-hint">
          {candidates.length > 0 ? (
            <p>
              {candidates.length} page{candidates.length === 1 ? "" : "s"} one link away from what was read, dashed on the graph. Click one to mark it as missed.
            </p>
          ) : (
            <p>Every cited page is lit. Click one to flag a bad citation.</p>
          )}
          {picked && pickedRole === "cited" && (
            <Button variant="outline" size="sm" className="self-start" data-testid="mark-bad" onClick={() => useReplay.getState().toggleBad(picked)}>
              {bad.includes(picked) ? "Remove the bad citation mark" : "Mark as a bad citation"}
              <span className="max-w-40 truncate font-normal text-muted-foreground">{title(picked)}</span>
            </Button>
          )}
          {(missed.length > 0 || bad.length > 0) && <p>Marks ride on your next message.</p>}
        </div>
      )}
    </div>
  );
}
