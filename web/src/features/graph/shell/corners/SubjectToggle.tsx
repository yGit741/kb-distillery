import { useRef } from "react";
import { useVariant } from "@/components/variants";
import { cn } from "@/lib/utils";
import type { GraphSubject } from "../../colourDimensions";
import { SUBJECTS } from "../../subject";
import { placeFor, SEARCH_LINE_H, SWITCH_H, useFrameWidth, VIEW_SWITCH_IDS, viewSwitchBox, type ViewSwitchPlace } from "../layout";

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** The switch's place beside the search line (variant `view-switch`, chosen in System → Variants). */
export function useViewSwitchPlace(): ViewSwitchPlace {
  return useVariant("view-switch", VIEW_SWITCH_IDS, "quiet")[0] as ViewSwitchPlace;
}

/** Line icons for the icon-only variant: three linked rings for concepts, a page for sources. */
function SubjectIcon({ id }: { id: GraphSubject }) {
  const common = { viewBox: "0 0 16 16", className: "size-4", fill: "none", stroke: "currentColor", strokeWidth: 1.4, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (id === "sources")
    return (
      <svg {...common}>
        <path d="M4 2.5h5.5L12 5v8.5H4z" />
        <path d="M9.5 2.5V5H12M6 8h4M6 10.5h4" />
      </svg>
    );
  return (
    <svg {...common}>
      <circle cx="4" cy="11" r="2" />
      <circle cx="12" cy="11" r="2" />
      <circle cx="8" cy="4.5" r="2" />
      <path d="M5.1 9.4 7 6.2M10.9 9.4 9 6.2M6 11h4" />
    </svg>
  );
}

/**
 * Concepts / Sources (flag graph-intent): what the graph is about. It sits beside the search line, never inside it:
 * the line stays the one place to search, ask, run a command, or switch views by typing ("sources"). Where exactly
 * is the `view-switch` variant; `viewSwitchBox` gives the line and the switch one geometry so they meet exactly.
 * It always reads Concepts / Sources: Health (flag knowledge-health) is a lens on concepts, reached by typing "health".
 */
export function SubjectToggle({ subject, onPick, top }: { subject: GraphSubject; onPick: (s: GraphSubject) => void; top: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const place = placeFor(useViewSwitchPlace(), useFrameWidth(ref));
  const box = viewSwitchBox(place);
  const icons = place === "icons";
  const words = place === "words";
  const dock = place === "dock";
  const tab = place === "tab";
  return (
    <div
      ref={ref}
      role="radiogroup"
      aria-label="What the graph shows"
      data-corners="subject"
      data-tour="graph-subject"
      data-place={place}
      className={cn(
        "pointer-events-auto absolute flex items-center text-[13px]",
        // a flat track, a shade off the page: no border, no shadow, so it never reads as a second input
        (place === "quiet" || icons) && "gap-0.5 rounded-lg bg-foreground/[0.05] p-0.5",
        words && "gap-4",
        dock && "gap-1 rounded-l-[14px] border border-r-0 bg-muted p-1 shadow-[var(--shadow)]",
        tab && "-translate-x-1/2 gap-0.5 rounded-b-[10px] border border-t-0 bg-card p-[3px] shadow-[var(--shadow)]",
      )}
      style={{ top: top + box.dy, left: box.left, width: box.width ?? undefined, height: tab ? undefined : dock ? SEARCH_LINE_H : SWITCH_H }}
    >
      {SUBJECTS.map((s) => {
        const on = subject === s.id;
        return (
          <button
            key={s.id}
            type="button"
            role="radio"
            aria-checked={on}
            aria-label={icons ? s.label : undefined}
            title={s.hint}
            onClick={() => onPick(s.id)}
            className={cn(
              "flex items-center justify-center whitespace-nowrap transition-[background-color,color,box-shadow] duration-150 motion-reduce:transition-none",
              words ? "h-8 px-0.5 underline-offset-[6px]" : "flex-1",
              (place === "quiet" || icons) && "h-7 rounded-md px-3",
              dock && "h-full rounded-[10px] px-3",
              tab && "h-6 rounded-[7px] px-2.5 text-[12px]",
              on
                ? words
                  ? "font-medium text-foreground underline decoration-foreground/50 decoration-2"
                  : "bg-card font-medium text-foreground shadow-[0_0_0_1px_var(--border)]"
                : "text-muted-foreground hover:text-foreground",
              RING,
            )}
          >
            {icons ? <SubjectIcon id={s.id} /> : s.label}
          </button>
        );
      })}
    </div>
  );
}
