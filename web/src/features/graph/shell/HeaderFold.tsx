import { ChevronDown } from "lucide-react";
import { useEffect } from "react";
import { useHeaderFold } from "@/app/headerFold";
import { cn } from "@/lib/utils";

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Flag `header-fold`: the chevron at the top edge of the graph, centred above the search line. Folded, it points
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
  return (
    <div
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
