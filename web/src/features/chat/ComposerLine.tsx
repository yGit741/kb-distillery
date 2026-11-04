import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  BILLINGS, BILLING_HINT, BILLING_LABEL, CAP_CHOICES, DEFAULT_CONTEXT, EFFORTS, EFFORT_LABEL,
  answerCap, capLabel, useComposer, usd, type Billing, type Effort,
} from "./composer";
import { fmtNum } from "./format";
import type { Model } from "./status";

interface Option {
  value: string;
  label: string;
  hint?: string;
}

/** A setting written as plain text; clicking opens its few choices just above it. */
function Choice({ name, value, options, onPick }: { name: string; value: string; options: Option[]; onPick: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const current = options.find((o) => o.value === value);
  return (
    <span ref={box} className="relative">
      <button
        type="button"
        aria-label={name}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((o) => !o)}
        className="rounded px-1 py-1 hover:bg-accent hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
      >
        {current?.label ?? value}
      </button>
      {open && (
        <ul id={id} role="listbox" aria-label={name} className="absolute bottom-full left-0 z-20 mb-1 min-w-36 rounded-md border bg-popover p-1 text-popover-foreground shadow-sm">
          {options.map((o) => (
            <li key={o.value} role="option" aria-selected={o.value === value}>
              <button
                type="button"
                title={o.hint}
                onClick={() => {
                  onPick(o.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-baseline justify-between gap-3 whitespace-nowrap rounded px-2 py-1 text-left hover:bg-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring",
                  o.value === value && "font-medium",
                )}
              >
                {o.label}
                {o.hint && <span className="text-[11px] font-normal text-muted-foreground">{o.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}

const SEP = (
  <span aria-hidden className="select-none">
    ·
  </span>
);

/** An arc of the 18px ring from twelve o'clock, clockwise, as a path (a full turn is two half arcs). */
function arc(frac: number, r = 7, c = 9): string {
  if (frac >= 0.999) return `M ${c} ${c - r} A ${r} ${r} 0 1 1 ${c} ${c + r} A ${r} ${r} 0 1 1 ${c} ${c - r}`;
  const a = 2 * Math.PI * frac;
  return `M ${c} ${c - r} A ${r} ${r} 0 ${frac > 0.5 ? 1 : 0} 1 ${(c + r * Math.sin(a)).toFixed(3)} ${(c - r * Math.cos(a)).toFixed(3)}`;
}

/** One thin ring: how much of the model's context the latest answer filled. */
export function ContextRing({ used, max }: { used: number; max: number }) {
  const frac = max > 0 ? Math.min(1, used / max) : 0;
  const pct = Math.round(frac * 100);
  const label = `Context about ${pct}% used (${fmtNum(used)} of ${fmtNum(max)} tokens)`;
  return (
    <span role="img" aria-label={label} title={label} data-testid="context-ring" data-fill={pct} className={cn("inline-flex", frac >= 0.9 ? "text-warn" : "text-muted-foreground")}>
      <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d={arc(1)} strokeOpacity="0.3" />
        {frac > 0 && <path d={arc(frac)} />}
      </svg>
    </span>
  );
}

interface Props {
  /** who pays until the user picks in the line: the Session panel's account */
  account: Billing;
  models: Model[];
  model: string;
  onModel: (id: string) => void;
}

/** Flag `agent-mode`: model, effort, who pays and the per-turn cap as one quiet line, the context ring at its end. */
export function ComposerLine({ account, models, model, onModel }: Props) {
  const prefs = useComposer((s) => s.prefs);
  const setPrefs = useComposer((s) => s.setPrefs);
  const capPrompt = useComposer((s) => s.capPrompt);
  const used = useComposer((s) => s.used);
  const max = models.find((m) => m.id === model)?.context ?? DEFAULT_CONTEXT;
  return (
    <div className="flex flex-col gap-1" data-testid="composer-line">
      {capPrompt && (
        <div role="alert" data-testid="cap-prompt" className="flex flex-wrap items-center gap-2 text-sm">
          <span>Continue? (spent {usd(capPrompt.spent)} of {usd(capPrompt.limit)})</span>
          <Button type="button" variant="outline" size="sm" onClick={() => answerCap("continue")}>
            Continue
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => answerCap("stop")}>
            Stop
          </Button>
        </div>
      )}
      <div className="-ml-1 flex flex-wrap items-center gap-x-0.5 text-xs text-muted-foreground" role="group" aria-label="How the next message runs">
        <Choice name="Model" value={model} options={models.map((m) => ({ value: m.id, label: m.label }))} onPick={onModel} />
        {SEP}
        <Choice name="Effort" value={prefs.effort} options={EFFORTS.map((e) => ({ value: e, label: EFFORT_LABEL[e] }))} onPick={(v) => setPrefs({ effort: v as Effort })} />
        {SEP}
        <Choice
          name="Billing"
          value={prefs.billing ?? account}
          options={BILLINGS.map((b) => ({ value: b, label: BILLING_LABEL[b], hint: BILLING_HINT[b] }))}
          onPick={(v) => setPrefs({ billing: v as Billing })}
        />
        {SEP}
        <Choice
          name="Cost cap per turn"
          value={String(prefs.cap)}
          options={CAP_CHOICES.map((c) => ({ value: String(c), label: capLabel(c) }))}
          onPick={(v) => setPrefs({ cap: Number(v) })}
        />
        <span className="ml-auto pl-2">
          <ContextRing used={used} max={max} />
        </span>
      </div>
    </div>
  );
}
