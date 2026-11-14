import { ChevronDown } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { useHeaderFold } from "@/app/headerFold";
import { cn } from "@/lib/utils";

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Flag `header-fold`: the chevron at the top edge of the graph, centred above the search line (not the frame: the
 * Concepts / Sources switch left of the line moves the line's centre to the right, and the chevron follows it). Folded, it points
 * down and opens the app bar (a 200 ms slide, none under reduced motion); open, it points up under the bar's
 * hairline, and the invisible 24px strip along that hairline folds the bar again on a double click.
 */
export function HeaderFold() {
  const setMounted = useHeaderFold((s) => s.setMounted);
  // the bar folds only while this chevron is on screen, so every other state and route keeps its bar
  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, [setMounted]);
  const folded = useHeaderFold((s) => s.folded);
  const toggle = useHeaderFold((s) => s.toggle);
  const label = folded ? "Show the app bar" : "Hide the app bar";
  const strip = useRef<HTMLDivElement>(null);
  const dx = useLineCentre(strip);
  return (
    <div
      ref={strip}
      data-testid="header-fold"
      data-folded={folded || undefined}
      className="pointer-events-auto absolute inset-x-0 top-0 z-[31] flex h-3.5 justify-center"
      title={folded ? "Double-click here to show the app bar" : "Double-click here to hide the app bar"}
      onDoubleClick={(e) => {
        // the chevron handles its own clicks; a double click on the strip around it folds or unfolds the bar, so
        // the same spot (the top edge of the graph) works both ways
        if (e.target instanceof HTMLElement && e.target.closest("button")) return;
        toggle();
      }}
    >
      <button
        type="button"
        aria-label={label}
        title={label}
        aria-expanded={!folded}
        onClick={toggle}
        onDoubleClick={(e) => e.stopPropagation()}
        style={dx ? { transform: `translateX(${dx}px)` } : undefined}
        className={cn(
          "pointer-events-auto -my-[5px] flex h-6 w-9 items-center justify-center rounded-full bg-background text-muted-foreground shadow-[0_0_10px_6px_var(--background)] transition-colors hover:text-foreground motion-reduce:transition-none",
          RING,
        )}
      >
        <ChevronDown aria-hidden className={cn("size-[14px] transition-transform duration-200 motion-reduce:transition-none", !folded && "rotate-180")} strokeWidth={1.6} />
      </button>
    </div>
  );
}

/** How far the search line's centre sits right of this strip's centre, kept current as the frame and line resize. */
function useLineCentre(strip: RefObject<HTMLDivElement | null>): number {
  const [dx, setDx] = useState(0);
  useLayoutEffect(() => {
    const own = strip.current;
    const frame = own?.parentElement;
    if (!own || !frame) return;
    const measure = () => {
      const line = frame.querySelector<HTMLElement>("[data-testid=graph-shell]");
      if (!line) return setDx(0);
      const a = line.getBoundingClientRect();
      const b = own.getBoundingClientRect();
      setDx(Math.round(a.left + a.width / 2 - (b.left + b.width / 2)));
    };
    if (typeof ResizeObserver === "undefined") return measure();
    const ro = new ResizeObserver(measure);
    let line: HTMLElement | null = null;
    // the line can mount after this strip, or be rebuilt (a flag or the full chat): follow it whenever the frame's
    // children change, and measure again
    const follow = () => {
      const now = frame.querySelector<HTMLElement>("[data-testid=graph-shell]");
      if (now !== line) {
        if (line) ro.unobserve(line);
        line = now;
        if (line) ro.observe(line);
      }
      measure();
    };
    ro.observe(own);
    follow();
    const mo = new MutationObserver(follow);
    mo.observe(frame, { childList: true });
    return () => {
      ro.disconnect();
      mo.disconnect();
    };
  }, [strip]);
  return dx;
}
