import { useEffect, useRef, useState } from "react";
import { useFlag } from "@/flags/useFlag";
import { cn } from "@/lib/utils";
import type { KeyRow } from "../../legendModel";
import { useReducedMotion } from "./motion";
import { useCorners } from "./cornersStore";
import { legendHeight, legendTop, LEGEND_OPEN_ROW, LEGEND_PAD, LEGEND_REST_ROW } from "./geometry";

interface Props {
  rows: readonly KeyRow[];
  /** "theme", "citation role": what the colour answers */
  title: string;
  hidden: ReadonlySet<string>;
  /** an ordered scale cannot hide pages by value */
  toggleable: boolean;
  onToggle: (label: string) => void;
  areaHeight: number;
  thinkCards: number;
}

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
/** legend-counts: the slide-out lists this many themes, the rest sit behind "+N more" */
export const LEGEND_TOP = 5;
const FULL_MS = 315; // the mockup's --k (.35) x .9s

/**
 * The colour legend: a tight stack of dots on the right edge, 8px from it. Press it and it spreads into the
 * names (with counts); pressing a name hides or shows that value, like the old legend did. While the Think fan is
 * open the stack moves down out of the fan's arc, so the two never overlap.
 */
export function ColourDots({ rows, title, hidden, toggleable, onToggle, areaHeight, thinkCards }: Props) {
  const open = useCorners((s) => s.order.includes("legend"));
  const thinkOpen = useCorners((s) => s.order.includes("think"));
  const toggle = useCorners((s) => s.toggle);
  const MS = useReducedMotion() ? 0 : FULL_MS;
  const box = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  // folding it while a name has the focus hands the focus back to the folded dots
  useEffect(() => {
    if (!open && box.current?.contains(document.activeElement) && document.activeElement !== opener.current) opener.current?.focus();
  }, [open]);
  const counts = useFlag("legend-counts");
  const [all, setAll] = useState(false);
  useEffect(() => {
    if (!open) setAll(false);
  }, [open]);
  if (!rows.length) return null;
  // an ordered scale reads in order, so only a categorical one is cut to its top themes
  const cut = counts && toggleable && rows.length > LEGEND_TOP + 1;
  const listed = cut && !all ? LEGEND_TOP : rows.length;
  const h = legendHeight(open ? listed + (cut ? 1 : 0) : rows.length, open);
  const top = legendTop({ areaHeight, height: h, thinkOpen, thinkCards });
  return (
    <div
      ref={box}
      role="group"
      aria-label={`Colour legend: colour is ${title}`}
      data-corners="legend"
      data-tour="graph-legend"
      data-open={open}
      data-shifted={thinkOpen}
      className={cn(
        "pointer-events-none absolute right-0 z-[18] flex flex-col items-end rounded-[14px] transition-[top,background-color,box-shadow] motion-reduce:transition-none",
        open ? "bg-card shadow-[var(--shadow)]" : "bg-transparent",
      )}
      style={{ top, paddingTop: LEGEND_PAD, paddingBottom: LEGEND_PAD, paddingLeft: open ? 12 : 8, paddingRight: 8, transitionDuration: `${MS}ms` }}
    >
      {!open && (
        <button
          ref={opener}
          type="button"
          aria-label={`Show colour names, colour is ${title}`}
          title={`Colour is ${title}: press to show the names`}
          aria-expanded={false}
          className={cn("pointer-events-auto absolute inset-0 rounded-[14px]", RING)}
          onClick={() => toggle("legend")}
        />
      )}
      <div
        className="overflow-hidden whitespace-nowrap text-[10px] font-medium uppercase tracking-wide text-muted-foreground transition-[height,opacity]"
        style={{ height: open ? 22 : 0, opacity: open ? 1 : 0, transitionDuration: `${MS}ms` }}
      >
        <button type="button" tabIndex={open ? 0 : -1} aria-label={`Colour = ${title}: hide names`} aria-expanded={open} title="Hide the names" className={cn("pointer-events-auto rounded px-1", RING)} onClick={() => toggle("legend")}>
          Colour = {title}
        </button>
      </div>
      {rows.map((r, i) => {
        const off = hidden.has(r.label);
        const away = open && i >= listed;
        return (
          <button
            key={r.label}
            type="button"
            tabIndex={open && !away ? 0 : -1}
            aria-hidden={!open || away}
            aria-pressed={toggleable ? !off : undefined}
            aria-disabled={!toggleable || undefined}
            title={toggleable ? `${off ? "Show" : "Hide"} ${r.label} (${r.count})` : `${r.label} (${r.count})`}
            data-row={r.label}
            onClick={() => toggleable && onToggle(r.label)}
            className={cn("flex items-center justify-end rounded-md transition-[height] motion-reduce:transition-none", open && !away ? "pointer-events-auto hover:bg-accent" : "pointer-events-none", away && "overflow-hidden", RING)}
            style={{ height: away ? 0 : open ? LEGEND_OPEN_ROW : LEGEND_REST_ROW, transitionDuration: `${MS}ms` }}
          >
            <span
              className={cn("max-w-0 overflow-hidden whitespace-nowrap text-[12.5px] opacity-0 transition-[max-width,opacity,margin]", open && "mr-2.5 max-w-[170px] opacity-100", off && "text-muted-foreground line-through")}
              style={{ transitionDuration: `${MS}ms`, transitionDelay: `${i * 14}ms` }}
            >
              {r.label}
            </span>
            <small
              className={cn("max-w-0 overflow-hidden whitespace-nowrap text-[11.5px] text-muted-foreground opacity-0 transition-[max-width,opacity,margin]", open && "mr-2.5 max-w-[30px] opacity-100")}
              style={{ transitionDuration: `${MS}ms`, transitionDelay: `${i * 14}ms` }}
            >
              <span className={counts ? "tabular-nums" : undefined}>{r.count}</span>
            </small>
            <i
              aria-hidden
              className={cn("block size-3 flex-none rounded-full transition-opacity", off && "opacity-30")}
              style={{ background: r.color, boxShadow: open ? "none" : "0 0 0 1.5px var(--background)" }}
            />
          </button>
        );
      })}
      {cut && (
        <button
          type="button"
          tabIndex={open ? 0 : -1}
          aria-hidden={!open}
          aria-expanded={all}
          data-more
          onClick={() => setAll((v) => !v)}
          className={cn("flex items-center justify-end overflow-hidden whitespace-nowrap rounded-md text-[12px] text-muted-foreground hover:bg-accent hover:text-foreground motion-reduce:transition-none", open ? "pointer-events-auto mr-[22px] min-w-[24px] px-2" : "pointer-events-none", RING)}
          style={{ height: open ? LEGEND_OPEN_ROW : 0, transition: `height ${MS}ms` }}
        >
          {all ? "Show fewer" : `+${rows.length - LEGEND_TOP} more`}
        </button>
      )}
    </div>
  );
}
