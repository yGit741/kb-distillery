import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { Hunk, RenderPage } from "@/api";
import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";
import { CHANGE_LABEL, changeKind, segments, type Segment } from "./model";
import { HunkControls, KIND_BAR, MarkedText, WhyLine, type HunkCtx } from "./parts";

export const DIFF_VIEWS = ["inline", "side-by-side", "reading"] as const;
export type DiffView = (typeof DIFF_VIEWS)[number];
export const DEFAULT_DIFF_VIEW: DiffView = "inline";

export interface DiffProps {
  page: RenderPage | undefined;
  slug: string;
  hunks: Hunk[];
  ctx: (h: Hunk) => HunkCtx;
}

const prose = "prose-sm max-w-none text-[15px] leading-7";

function Same({ blocks }: { blocks: { index: number; text: string }[] }) {
  return <Markdown className={prose}>{blocks.map((b) => b.text).join("")}</Markdown>;
}

/** The frame every hunk gets: an anchor for j/k, a focus ring, a quiet dim once rejected. */
function HunkFrame({ hunk, ctx, className, children }: { hunk: Hunk; ctx: HunkCtx; className?: string; children: ReactNode }) {
  return (
    <section
      data-hunk={hunk.id}
      data-focused={ctx.focused || undefined}
      data-decision={ctx.decision}
      aria-label={`Change: ${CHANGE_LABEL[changeKind(hunk)]}`}
      onClick={ctx.onFocus}
      className={cn(
        "scroll-mt-24 rounded-lg transition-[box-shadow,opacity] duration-200",
        ctx.focused ? "ring-1 ring-ring/40" : "ring-0",
        ctx.decision === "reject" && "opacity-60",
        className,
      )}
    >
      {children}
    </section>
  );
}

/** inline: the page as it reads; changed blocks carry word marks and their controls in the right margin. */
export function InlineDiff({ page, hunks, ctx }: DiffProps) {
  return (
    <div className="flex flex-col gap-3">
      {segments(page, hunks).map((seg, i) =>
        seg.kind === "same" ? (
          <div key={i} className="pr-48">
            <Same blocks={seg.blocks} />
          </div>
        ) : (
          <HunkFrame key={seg.hunk.id} hunk={seg.hunk} ctx={ctx(seg.hunk)} className="-ml-3 grid grid-cols-[minmax(0,1fr)_11rem] gap-4 py-2 pl-3">
            <div>
              <MarkedText hunk={seg.hunk} className="text-[15px]" />
              <WhyLine hunk={seg.hunk} />
            </div>
            <div className="border-l pl-3">
              <HunkControls ctx={ctx(seg.hunk)} />
            </div>
          </HunkFrame>
        ),
      )}
    </div>
  );
}

function Fold({ seg }: { seg: Extract<Segment, { kind: "same" }> }) {
  const [open, setOpen] = useState(false);
  const n = seg.blocks.length;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex h-7 w-full items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground hover:bg-accent/60"
      >
        <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} aria-hidden />
        {n} unchanged {n === 1 ? "paragraph" : "paragraphs"}
      </button>
      {open && (
        <div className="grid grid-cols-2 gap-6 px-2 pt-1 text-muted-foreground">
          <Same blocks={seg.blocks} />
          <Same blocks={seg.blocks} />
        </div>
      )}
    </div>
  );
}

/** side-by-side: before | after per block, unchanged runs folded to one line, controls under the pair. */
export function SideBySideDiff({ page, hunks, ctx }: DiffProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-6 px-3 text-xs font-medium text-muted-foreground">
        <span>Before</span>
        <span>After</span>
      </div>
      {segments(page, hunks).map((seg, i) =>
        seg.kind === "same" ? (
          <Fold key={i} seg={seg} />
        ) : (
          <HunkFrame key={seg.hunk.id} hunk={seg.hunk} ctx={ctx(seg.hunk)} className="border bg-card px-3 py-3">
            <div className="grid grid-cols-2 gap-6">
              <div className="min-w-0">
                {seg.hunk.before.trim() ? <MarkedText hunk={seg.hunk} show="before" className="text-[15px]" /> : <p className="text-xs italic text-muted-foreground">nothing here before</p>}
              </div>
              <div className="min-w-0 border-l pl-6">
                {seg.hunk.after.trim() ? <MarkedText hunk={seg.hunk} show="after" className="text-[15px]" /> : <p className="text-xs italic text-muted-foreground">removed</p>}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-start justify-between gap-x-4 gap-y-1 border-t pt-2">
              <div className="min-w-0 flex-1">
                <WhyLine hunk={seg.hunk} />
              </div>
              <HunkControls ctx={ctx(seg.hunk)} layout="row" />
            </div>
          </HunkFrame>
        ),
      )}
    </div>
  );
}

/** reading: the finished page, clean; a thin bar in the left gutter marks each change and opens a margin note. */
export function ReadingDiff({ page, hunks, ctx }: DiffProps) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-3">
      {segments(page, hunks).map((seg, i) => {
        if (seg.kind === "same")
          return (
            <div key={i} className="grid grid-cols-[1rem_minmax(0,1fr)_16rem] gap-3">
              <span />
              <Same blocks={seg.blocks} />
              <span />
            </div>
          );
        const h = seg.hunk;
        const c = ctx(h);
        const kind = changeKind(h);
        const shown = open === h.id || (open === null && c.focused) || c.correcting;
        return (
          <HunkFrame key={h.id} hunk={h} ctx={{ ...c, focused: false }} className="grid grid-cols-[1rem_minmax(0,1fr)_16rem] gap-3">
            <button
              type="button"
              aria-label={`${CHANGE_LABEL[kind]}: show what changed`}
              title={`${CHANGE_LABEL[kind]}: show what changed`}
              aria-expanded={shown}
              onClick={(e) => {
                e.stopPropagation();
                c.onFocus();
                setOpen(open === h.id ? null : h.id);
              }}
              className="group flex justify-center py-1"
            >
              <span className={cn("block w-[3px] rounded-full transition-[width] group-hover:w-[5px]", KIND_BAR[kind], c.focused && "w-[5px]", kind === "delete" && "min-h-4")} />
            </button>
            <div className={cn("min-w-0", c.decision === "reject" && "opacity-60")}>
              {h.after.trim() ? <Markdown className={prose}>{h.after}</Markdown> : <p className="py-1 text-xs italic text-muted-foreground">A passage is removed here.</p>}
            </div>
            <aside className="relative min-w-0">
              {shown && (
                <div className="absolute inset-x-0 top-0 z-10 rounded-lg border bg-card p-3 text-sm shadow-sm" data-testid="margin-note">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">{h.before.trim() ? "Before" : "New text"}</p>
                  {h.before.trim() && <MarkedText hunk={h} show="before" className="text-sm leading-6 text-foreground/85" />}
                  <WhyLine hunk={h} />
                  <div className="mt-2 border-t pt-2">
                    <HunkControls ctx={c} />
                  </div>
                </div>
              )}
              {!shown && c.decision && <p className="pt-1 text-xs text-muted-foreground">{c.decision === "accept" ? "Accepted" : c.decision === "reject" ? "Rejected" : "Correction noted"}</p>}
            </aside>
          </HunkFrame>
        );
      })}
    </div>
  );
}

export const DIFF_COMPONENT: Record<DiffView, (p: DiffProps) => ReactNode> = {
  inline: InlineDiff,
  "side-by-side": SideBySideDiff,
  reading: ReadingDiff,
};
