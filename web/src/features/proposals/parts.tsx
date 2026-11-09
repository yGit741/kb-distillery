import { Link } from "@tanstack/react-router";
import { Check, MessageSquare, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Decision, Hunk } from "@/api";
import { cn } from "@/lib/utils";
import { pageTo } from "@/features/pages/parts";
import { readable, type ChangeKind } from "./model";

/** What one hunk control row needs from the screen. */
export interface HunkCtx {
  decision?: Decision;
  comment?: string;
  focused: boolean;
  /** Older revision on screen, or the proposal is closed: the controls are shown but off. */
  readOnly: boolean;
  correcting: boolean;
  onDecide: (d: Decision, comment?: string) => void;
  onCorrect: (open: boolean) => void;
  onFocus: () => void;
  /** Replaces Accept / Reject / Correct with one action button (page history: "Restore block"). */
  action?: { label: string; onClick: () => void; disabled?: boolean; note?: string };
}

/** Word marks for a hunk's tokens. `show` picks which side: both (inline), before only, after only. */
export function Tokens({ tokens, show = "both" }: { tokens: string[][]; show?: "both" | "before" | "after" }) {
  return (
    <>
      {tokens.map(([op, text], i) => {
        if (op === "insert" && show === "before") return null;
        if (op === "delete" && show === "after") return null;
        const t = readable(text ?? "");
        if (op === "insert") return <ins key={i} className="rounded-sm bg-ok/15 px-px text-foreground underline decoration-ok/60 underline-offset-4">{t}</ins>;
        if (op === "delete") return <del key={i} className="rounded-sm bg-bad/10 px-px text-foreground/80 decoration-bad/70">{t}</del>;
        return <span key={i}>{t}</span>;
      })}
    </>
  );
}

/** The block's text with its marks, laid out like prose (paragraph breaks kept). */
export function MarkedText({ hunk, show = "both", className }: { hunk: Hunk; show?: "both" | "before" | "after"; className?: string }) {
  const heading = /^#{1,6}\s/.test((show === "before" ? hunk.before : hunk.after || hunk.before).trimStart());
  return (
    <div className={cn("whitespace-pre-wrap break-words leading-7", heading && "text-lg font-semibold", className)}>
      <Tokens tokens={trimTokens(hunk.tokens)} show={show} />
    </div>
  );
}

/** Drop trailing blank-line tokens so a block does not end in empty lines. */
function trimTokens(tokens: string[][]): string[][] {
  const out = tokens.map((t) => [...t]);
  while (out.length && !(out[out.length - 1]![1] ?? "").trim()) out.pop();
  const last = out[out.length - 1];
  if (last) last[1] = (last[1] ?? "").replace(/\s+$/, "");
  return out;
}

const STATE: Record<Decision, { label: string; icon: typeof Check }> = {
  accept: { label: "Accepted", icon: Check },
  reject: { label: "Rejected", icon: X },
  correct: { label: "Correction noted", icon: MessageSquare },
};

/** Accept / Reject / Correct for one hunk, the quiet state mark once decided, and the inline correction box. */
export function HunkControls({ ctx, layout = "column", correct = true }: { ctx: HunkCtx; layout?: "column" | "row"; correct?: boolean }) {
  const { decision, readOnly } = ctx;
  if (ctx.action) {
    const a = ctx.action;
    return (
      <div className="flex flex-col items-start gap-1" data-testid="hunk-controls">
        <button
          type="button"
          disabled={a.disabled}
          onClick={(e) => {
            e.stopPropagation();
            ctx.onFocus();
            a.onClick();
          }}
          className="h-7 rounded-md px-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
        >
          {a.label}
        </button>
        {a.note && <p className="text-xs text-muted-foreground">{a.note}</p>}
      </div>
    );
  }
  const btn = (d: Decision, label: string, key: string) => (
    <button
      type="button"
      disabled={readOnly}
      aria-pressed={decision === d}
      aria-keyshortcuts={key}
      onClick={(e) => {
        e.stopPropagation();
        ctx.onFocus();
        if (d === "correct") ctx.onCorrect(!ctx.correcting);
        else ctx.onDecide(d);
      }}
      className={cn(
        "h-7 rounded-md px-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-50",
        decision === d && "bg-muted font-medium text-foreground",
      )}
    >
      {label}
    </button>
  );
  const mark = decision ? STATE[decision] : null;
  return (
    <div className={cn("flex gap-2", layout === "column" ? "flex-col items-stretch" : "flex-wrap items-center")} data-testid="hunk-controls">
      <div className={cn("flex items-center gap-0.5", layout === "column" && "justify-start")}>
        {btn("accept", "Accept", "a")}
        {btn("reject", "Reject", "r")}
        {correct && btn("correct", "Correct", "c")}
      </div>
      <p className="flex h-5 items-center gap-1.5 text-xs text-muted-foreground" data-testid="hunk-state">
        {mark && (
          <>
            <mark.icon className="size-3.5" aria-hidden />
            {mark.label}
          </>
        )}
      </p>
      {ctx.correcting && <CorrectBox initial={ctx.comment ?? ""} onCancel={() => ctx.onCorrect(false)} onSave={(c) => ctx.onDecide("correct", c)} />}
      {!ctx.correcting && decision === "correct" && ctx.comment && <p className="text-xs italic text-muted-foreground">"{ctx.comment}"</p>}
    </div>
  );
}

function CorrectBox({ initial, onSave, onCancel }: { initial: string; onSave: (c: string) => void; onCancel: () => void }) {
  const [text, setText] = useState(initial);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const save = () => text.trim() && onSave(text.trim());
  return (
    <div className="flex w-full flex-col gap-1.5" onClick={(e) => e.stopPropagation()}>
      <textarea
        ref={ref}
        value={text}
        rows={3}
        aria-label="What should change?"
        placeholder="What should change?"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onCancel();
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
        }}
        className="w-full resize-y rounded-md border bg-background px-2 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <div className="flex justify-end gap-1">
        <button type="button" onClick={onCancel} className="h-7 rounded-md px-2.5 text-xs text-muted-foreground hover:bg-accent">
          Cancel
        </button>
        <button type="button" onClick={save} disabled={!text.trim()} className="h-7 rounded-md bg-secondary px-2.5 text-xs font-medium hover:bg-accent disabled:opacity-50">
          Save note
        </button>
      </div>
    </div>
  );
}

/** The muted line under a block: why the producer made the change and the pages it drew on. */
export function WhyLine({ hunk, extra }: { hunk: Hunk; extra?: ReactNode }) {
  const links = [...hunk.links_added.map((l) => `link added: ${l}`), ...hunk.links_removed.map((l) => `link removed: ${l}`)];
  if (!hunk.reason && !hunk.sources.length && !links.length && !extra) return null;
  return (
    <p className="mt-1.5 text-xs leading-5 text-muted-foreground" data-testid="why-line">
      {hunk.reason && <span>why: {hunk.reason}</span>}
      {hunk.sources.length > 0 && (
        <span>
          {hunk.reason && " · "}from:{" "}
          {hunk.sources.map((s, i) => (
            <span key={s}>
              {i > 0 && ", "}
              <Link to={pageTo(s)} className="underline decoration-border underline-offset-2 hover:text-foreground" onClick={(e) => e.stopPropagation()}>
                {s}
              </Link>
            </span>
          ))}
        </span>
      )}
      {links.length > 0 && <span>{(hunk.reason || hunk.sources.length) && " · "}{links.join(" · ")}</span>}
      {extra}
    </p>
  );
}

/** The one colour ramp of a change kind (gutter bars, legend). Insert green, delete red, modified the accent. */
export const KIND_BAR: Record<ChangeKind, string> = { insert: "bg-ok/70", delete: "bg-bad/70", modified: "bg-primary/70" };
