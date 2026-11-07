import { X } from "lucide-react";
import { useThinking } from "./thinkingStore";

/**
 * What the thinking view's marks mean (flag `show-thinking`), under the graph while it shows an answer, with the
 * one-click way out. The swatches are neutral ink: on the graph each page glows in its own colour.
 */
export function ThinkingLegend({ web }: { web: boolean }) {
  const mark = "relative inline-block size-3 shrink-0 rounded-full border-[1.5px] border-foreground";
  return (
    <div
      aria-label="Show my thinking legend"
      data-testid="thinking-legend"
      className="pointer-events-auto absolute bottom-3 right-3 z-10 flex items-start gap-2 rounded-xl border bg-card/95 py-2 pl-3 pr-1.5 text-xs text-muted-foreground shadow-[var(--shadow)]"
    >
      <ul className="flex flex-col gap-1">
        <li className="font-medium text-foreground">Colour = part of this answer</li>
        <li className="flex items-center gap-2">
          <span aria-hidden className={`${mark} border-muted-foreground opacity-40`} /> not part of it
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className={mark} /> found in a result
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className={`${mark} shadow-[0_0_6px_2px_color-mix(in_oklab,var(--foreground)_30%,transparent)]`} /> opened
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className={`${mark} shadow-[0_0_9px_4px_color-mix(in_oklab,var(--foreground)_45%,transparent)]`} /> cited, with its number
        </li>
        {web && (
          <li className="flex items-center gap-2">
            <span aria-hidden className={`${mark} border-dashed border-muted-foreground`} /> web source, dashed: inferred link
          </li>
        )}
      </ul>
      <button
        type="button"
        aria-label="Hide the thinking view on the graph"
        title="Hide the thinking view on the graph"
        className="grid size-6 place-items-center rounded-md hover:bg-secondary hover:text-foreground"
        onClick={() => useThinking.getState().dismiss()}
      >
        <X aria-hidden strokeWidth={1.6} className="size-3.5" />
      </button>
    </div>
  );
}
