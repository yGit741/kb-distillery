import { useEffect, useMemo, useRef } from "react";
import { Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { ShapeIcon, SourceIcon } from "../../encoding/NodeMarkSvg";
import { markOf } from "../../encoding/spec";
import type { TypeRow } from "../../legendModel";
import { useReducedMotion } from "./motion";
import { useCorners } from "./cornersStore";
import { groupTypes, typeName, type TypeGroup } from "./typeGroups";
import { useStillClick } from "./useStillClick";

interface Props {
  concepts: readonly TypeRow[];
  /** sources, with the collections folded in */
  sources: readonly TypeRow[];
  /** show (on) or hide every one of these types */
  onToggle: (types: readonly string[], on: boolean) => void;
  /** spotlight the pages of these types while the pointer is on them (null = none) */
  onSpot: (types: readonly string[] | null) => void;
}

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const FULL_MS = 315; // the mockup's --k (.35) x .9s
const SPOT_IN_MS = 120;
const SPOT_OUT_MS = 160;
/** a group scrolls sideways (out of sight, from the centre outwards) when the screen is too narrow for all its names */
const GROUP = "flex h-6 min-w-0 max-w-full items-center overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden";

/**
 * The page types, at the bottom centre, 8px from the edge: folded, the marks sit in a tight row (concepts left of a
 * thin divider, sources right of it); pressed, ONE card opens around them and the marks unfold into names with
 * counts, concepts to the left and sources to the right, the divider staying at the centre of the screen. A
 * dimmed name is a type that is hidden (sources are by default). Types that share an icon are one name with their counts summed; pressing a name hides or shows all of them.
 */
export function TypesCard({ concepts, sources, onToggle, onSpot }: Props) {
  const MS = useReducedMotion() ? 0 : FULL_MS;
  const open = useCorners((s) => s.order.includes("types"));
  const toggle = useCorners((s) => s.toggle);
  const still = useStillClick(open, () => toggle("types"));
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  // folding it (Escape, a click outside) while a name has the focus hands the focus back to the folded marks
  useEffect(() => {
    if (!open && box.current?.contains(document.activeElement) && document.activeElement !== opener.current) opener.current?.focus();
  }, [open]);
  const spot = (types: readonly string[] | null) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onSpot(types), types ? SPOT_IN_MS : SPOT_OUT_MS);
  };
  const conceptGroups = useMemo(() => groupTypes(concepts), [concepts]);
  const sourceGroups = useMemo(() => groupTypes(sources), [sources]);
  if (!conceptGroups.length && !sourceGroups.length) return null;
  const both = conceptGroups.length > 0 && sourceGroups.length > 0;

  const item = (r: TypeGroup, side: "left" | "right", i: number) => {
    const label = r.label;
    const ids = r.members.map((m) => m.id);
    const lead = r.members[0]!;
    const icon = (
      <span key="i" className={cn("grid size-[15px] flex-none place-items-center rounded-full transition-colors", open ? "bg-transparent" : "bg-background")}>
        {lead.layer === "source" ? <SourceIcon type={r.id} className="size-3" /> : <ShapeIcon shape={markOf(r.id)} className="size-3" />}
      </span>
    );
    const text = (
      <span
        key="t"
        className={cn("flex items-baseline gap-[5px] overflow-hidden whitespace-nowrap text-[12.5px] leading-[15px] transition-[max-width,opacity,margin]", open ? "max-w-[120px] opacity-100" : "max-w-0 opacity-0", open && (side === "left" ? "mr-1.5" : "ml-1.5"))}
        style={{ transitionDuration: `${MS}ms`, transitionDelay: `${i * 16}ms` }}
      >
        {label}
        <small className="text-[11px] text-muted-foreground max-[1100px]:hidden">{r.total}</small>
      </span>
    );
    return (
      <button
        key={r.key}
        type="button"
        tabIndex={open ? 0 : -1}
        aria-hidden={!open}
        aria-pressed={r.shown}
        aria-label={`${label}, ${r.total}`}
        title={`${r.shown ? "Hide" : "Show"} every ${label.toLowerCase()}${r.members.length > 1 ? ` (${r.members.map((m) => `${typeName(m)} ${m.total}`).join(", ")})` : ""}`}
        data-type={r.id}
        onClick={() => open && onToggle(ids, !r.shown)}
        onMouseEnter={() => open && spot(ids)}
        onFocus={() => open && spot(ids)}
        onBlur={() => spot(null)}
        className={cn(
          "flex h-6 shrink-0 items-center rounded-lg transition-[margin,color] motion-reduce:transition-none",
          open ? "pointer-events-auto hover:bg-accent" : "pointer-events-none",
          r.shown ? "text-foreground" : "text-muted-foreground",
          !open && (side === "left" ? "-mr-[5px] first:mr-0" : "-ml-[5px] first:ml-0"),
          open && (side === "left" ? "mr-3 first:mr-0" : "ml-3 first:ml-0"),
          !open && !r.shown && "opacity-70",
          RING,
        )}
        style={{ transitionDuration: `${MS}ms` }}
      >
        {side === "left" ? [text, icon] : [icon, text]}
      </button>
    );
  };

  return (
    <div
      ref={box}
      role="group"
      aria-label="Page types"
      data-corners="types"
      data-tour="graph-types"
      data-open={open}
      onClickCapture={still.onClickCapture}
      data-groups={both ? 2 : 1}
      className={cn(
        "pointer-events-none absolute bottom-[3.5px] [.gt-active_&]:bottom-[76px] left-1/2 z-[24] grid h-6 w-max max-w-[calc(100%-160px)] -translate-x-1/2 items-center",
        // two groups meet at a divider that stays on the screen's centre; one group alone (the Concepts view) is
        // centred itself
        both ? "grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]" : "grid-cols-1 justify-items-center",
      )}
      onMouseLeave={() => spot(null)}
    >
      {/* the one card behind both groups, symmetric around the fixed centre */}
      <span
        aria-hidden
        className={cn("absolute -inset-x-3.5 -inset-y-[2.5px] -z-10 rounded-[14px] bg-card shadow-[var(--shadow)] transition-opacity duration-300 motion-reduce:transition-none", open ? "pointer-events-auto opacity-100" : "opacity-0")}
      />
      {open && (
        <button
          type="button"
          aria-label="Hide the page types"
          title="Hide the page types"
          className={cn("pointer-events-auto absolute -right-[38px] top-1/2 grid size-5 -translate-y-1/2 place-items-center rounded-full bg-card text-muted-foreground shadow-[var(--shadow)] hover:text-foreground", RING)}
          onClick={() => toggle("types")}
        >
          <Minus aria-hidden className="size-3" strokeWidth={1.6} />
        </button>
      )}
      {!open && (
        <button
          ref={opener}
          type="button"
          aria-label="Show page types"
          title="Page types: press to show the names"
          aria-expanded={false}
          className={cn("pointer-events-auto absolute -inset-x-3.5 -inset-y-[2.5px] cursor-pointer rounded-[14px] transition-colors hover:bg-accent motion-reduce:transition-none", RING)}
          onClick={(e) => {
            still.mark(e);
            toggle("types");
          }}
        />
      )}
      {both ? (
        <>
          <div className={`${GROUP} flex-row-reverse justify-self-end`}>{conceptGroups.map((r, i) => item(r, "left", i))}</div>
          <span aria-hidden className={cn("block w-px rounded-sm bg-border transition-[margin,height] motion-reduce:transition-none", open ? "mx-3.5 h-4" : "mx-2 h-3")} style={{ transitionDuration: `${MS}ms` }} />
          <div className={`${GROUP} justify-self-start`}>{sourceGroups.map((r, i) => item(r, "right", i))}</div>
        </>
      ) : (
        <div className={GROUP}>{(conceptGroups.length ? conceptGroups : sourceGroups).map((r, i) => item(r, "right", i))}</div>
      )}
    </div>
  );
}
