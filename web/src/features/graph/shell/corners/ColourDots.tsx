import { useEffect, useRef } from "react";
import { useFlag } from "@/flags/useFlag";
import { cn } from "@/lib/utils";
import type { Dimension } from "../../colourDimensions";
import type { KeyRow } from "../../legendModel";
import type { ColorBy } from "../../style";
import { useReducedMotion } from "./motion";
import { useCorners } from "./cornersStore";
import { EDGE, legendFoldDotY, legendHeight, legendTop, LEGEND_BAR_OPEN, LEGEND_BAR_REST, LEGEND_HEAD, LEGEND_OPEN_ROW, LEGEND_PAD, LEGEND_REST_ROW } from "./geometry";
import { useStillClick } from "./useStillClick";

interface Props {
  /** spotlight the pages of this colour value while the pointer or focus is on its row (null = none) */
  onSpot?: (label: string | null) => void;
  rows: readonly KeyRow[];
  /** "theme", "citation role": what the colour answers */
  title: string;
  /** the colouring in use, and the ones the header's dropdown offers for what is drawn */
  by: ColorBy;
  dimensions: readonly Dimension[];
  onPick: (by: ColorBy) => void;
  /** a continuous colouring: one gradient bar (its steps, low to high) with its two ends named, no swatches */
  bar?: { stops: readonly string[]; low: string; high: string };
  hidden: ReadonlySet<string>;
  /** an ordered scale cannot hide pages by value */
  toggleable: boolean;
  onToggle: (label: string) => void;
  areaHeight: number;
  thinkCards: number;
}

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
/** The hover spotlight settles before it lights, and lingers a little on the way out (as on the page types). */
const SPOT_IN_MS = 120;
const SPOT_OUT_MS = 160;
const FULL_MS = 315; // the mockup's --k (.35) x .9s

/**
 * The colour legend: a tight stack of dots on the right edge, 8px from it. Press it and it spreads into the
 * names (with counts) under a centred header, "Color by [dimension]", whose dimension is a quiet dropdown; pressing
 * a name hides or shows that value. A continuous colouring shows one gradient bar instead of dots. Two clicks on
 * the same spot open and close it (./useStillClick), so the second never lands on a name. While the Think fan is
 * open the stack moves down out of the fan's arc, so the two never overlap.
 */
export function ColourDots({ rows, title, by, dimensions, onPick, bar, hidden, toggleable, onToggle, areaHeight, thinkCards, onSpot }: Props) {
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
  // hover spotlight, like the page types: settle in, linger out, and let go when the card folds or unmounts
  const spotTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const spot = (label: string | null) => {
    if (!onSpot) return;
    if (spotTimer.current) clearTimeout(spotTimer.current);
    spotTimer.current = setTimeout(() => spotNow(label), label ? SPOT_IN_MS : SPOT_OUT_MS);
  };
  // clear only what this card lit, and only when it folds: another surface (the source-kind dial) shares spotIds
  const lit = useRef(false);
  const latest = useRef(onSpot);
  latest.current = onSpot;
  const spotNow = (label: string | null) => {
    if (!label && !lit.current) return;
    lit.current = !!label;
    latest.current?.(label);
  };
  useEffect(() => {
    if (open) return;
    if (spotTimer.current) clearTimeout(spotTimer.current);
    spotNow(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- spotNow reads refs; this runs on folding only
  }, [open]);
  useEffect(() => () => void (spotTimer.current && clearTimeout(spotTimer.current)), []);
  const still = useStillClick(open, () => toggle("legend"));
  if (!rows.length && !bar) return null;
  const known = dimensions.some((d) => d.by === by);
  // pressed, the card lists every colour; a long list scrolls inside the screen area instead of running off it
  const fit = Math.max(0, areaHeight - 2 * EDGE);
  const h = Math.min(bar ? 2 * LEGEND_PAD + (open ? LEGEND_BAR_OPEN : LEGEND_BAR_REST) : legendHeight(rows.length, open), fit || Infinity);
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
      onClickCapture={still.onClickCapture}
      className={cn(
        "absolute right-0 z-[18] flex flex-col items-end rounded-[14px] transition-[top,background-color,box-shadow] motion-reduce:transition-none",
        open ? "pointer-events-auto bg-card shadow-[var(--shadow)]" : "pointer-events-none bg-transparent",
      )}
      style={{ top, maxHeight: open && fit ? fit : undefined, overflowY: open ? "auto" : undefined, paddingTop: LEGEND_PAD, paddingBottom: LEGEND_PAD, paddingLeft: open ? 12 : 8, paddingRight: 8, transitionDuration: `${MS}ms` }}
    >
      {!open && (
        <button
          ref={opener}
          type="button"
          aria-label={`Show colour names, colour is ${title}`}
          title={`Colour is ${title}: press to show the names`}
          aria-expanded={false}
          className={cn("pointer-events-auto absolute inset-0 rounded-[14px]", RING)}
          onClick={(e) => {
            still.mark(e);
            toggle("legend");
          }}
        />
      )}
      <div
        data-row="header"
        className="relative flex items-center justify-center gap-0.5 self-stretch overflow-hidden whitespace-nowrap pr-4 text-[10px] font-medium uppercase tracking-wide text-muted-foreground transition-[height,opacity]"
        style={{ height: open ? LEGEND_HEAD : 0, opacity: open ? 1 : 0, transitionDuration: `${MS}ms` }}
      >
        <label className="group/pick pointer-events-auto relative flex h-full cursor-pointer items-center gap-1.5 rounded px-1 leading-3 hover:bg-accent">
          <span>Color by</span>
          {/* a thin rule under the coloured-by word says "this opens a choice", quieter than a chevron */}
          <span className="font-semibold text-foreground underline decoration-muted-foreground/60 decoration-1 underline-offset-[3px] group-hover/pick:decoration-foreground">
            {known ? dimensions.find((d) => d.by === by)?.label : title}
          </span>
          {/* the native select covers the label, invisible, so the whole phrase opens it */}
          <select
            tabIndex={open ? 0 : -1}
            aria-label="Color by"
            title="Choose what the colour shows"
            value={known ? by : ""}
            onChange={(e) => onPick(e.target.value as ColorBy)}
            className={cn("absolute inset-0 cursor-pointer appearance-none opacity-0", RING)}
          >
            {!known && <option value="">{title}</option>}
            {dimensions.map((d) => (
              <option key={d.by} value={d.by}>
                {d.label}
              </option>
            ))}
          </select>
        </label>
        {/* folding: three small muted dots over the colour circles' column, halfway between the card's edge and the top circle */}
        <button
          type="button"
          tabIndex={open ? 0 : -1}
          aria-label="Hide the colour legend"
          aria-expanded={open}
          title="Hide the legend"
          className={cn("group pointer-events-auto absolute -right-0.5 flex h-4 w-4 items-center justify-center gap-[2px] rounded-full", RING)}
          // the header starts LEGEND_PAD below the card's edge; the 16px box is centred on the dots and on the circles' column
          style={{ top: legendFoldDotY(!!bar) - LEGEND_PAD - 8 }}
          onClick={() => toggle("legend")}
        >
          {[0, 1, 2].map((i) => (
            <i key={i} aria-hidden className="block size-[3px] rounded-full bg-muted-foreground/60 transition-colors group-hover:bg-foreground" />
          ))}
        </button>
      </div>
      {bar && (
        <div data-row="bar" className="flex flex-col items-stretch gap-1" style={{ width: open ? 168 : 10 }}>
          <i
            aria-hidden
            className="block rounded-full"
            style={{
              height: open ? 10 : LEGEND_BAR_REST,
              // at rest the bar stands on the edge like the dots, high on top; spread, it reads left (low) to right
              background: `linear-gradient(${open ? "to right" : "to top"}, ${bar.stops.join(", ")})`,
              boxShadow: open ? "none" : "0 0 0 1.5px var(--background)",
            }}
          />
          {open && (
            <span className="flex justify-between text-[11px] leading-tight text-muted-foreground">
              <span>{bar.low}</span>
              <span>{bar.high}</span>
            </span>
          )}
        </div>
      )}
      {!bar && rows.map((r, i) => {
        const off = hidden.has(r.label);
        return (
          <button
            key={r.label}
            type="button"
            tabIndex={open ? 0 : -1}
            aria-hidden={!open}
            aria-pressed={toggleable ? !off : undefined}
            aria-disabled={!toggleable || undefined}
            title={toggleable ? `${off ? "Show" : "Hide"} ${r.label} (${r.count})` : `${r.label} (${r.count})`}
            data-row={r.label}
            onClick={() => {
              if (!toggleable) return;
              onToggle(r.label);
              // the row just hid (or came back) under the pointer: light what is drawn now, at once
              if (spotTimer.current) clearTimeout(spotTimer.current);
              spotNow(off ? r.label : null);
            }}
            // a hidden value has nothing drawn to light up
            onMouseEnter={() => open && spot(off ? null : r.label)}
            onMouseLeave={() => spot(null)}
            onFocus={() => open && spot(off ? null : r.label)}
            onBlur={() => spot(null)}
            className={cn("flex items-center justify-end rounded-md transition-[height] motion-reduce:transition-none", open ? "pointer-events-auto hover:bg-accent" : "pointer-events-none", RING)}
            style={{ height: open ? LEGEND_OPEN_ROW : LEGEND_REST_ROW, transitionDuration: `${MS}ms` }}
          >
            <span
              // a long name (a topic named by the LLM) ends in an ellipsis; the full name is its tooltip
              title={r.label}
              className={cn("max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12.5px] opacity-0 transition-[max-width,opacity,margin]", open && "mr-2.5 max-w-[210px] opacity-100", off && "text-muted-foreground line-through")}
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
    </div>
  );
}
