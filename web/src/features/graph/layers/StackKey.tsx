import { cn } from "@/lib/utils";
import { marker } from "../shell/shape";
import { useGraphUi } from "../store";
import { legendRows } from "./model";
import { stackCurrent, useLayers } from "./store";

/**
 * What the view stack says about colours, sizes and links, as rows under the legend (flag graph-intent). It speaks only
 * while the stack is what is drawn: a change by hand retires it, and a removed layer takes its row along.
 */
export function StackKey({ className }: { className?: string }) {
  const stack = useLayers((s) => s.stack);
  const applied = useLayers((s) => s.applied);
  const live = useGraphUi((s) => stackCurrent(applied, marker(s)));
  const rows = legendRows(stack);
  if (!live || !rows.length) return null;
  return (
    <div role="group" aria-label="View layers" data-testid="stack-key" className={cn("pointer-events-auto flex flex-col gap-0.5 rounded-lg border bg-card/95 px-2 py-1 text-xs shadow-[var(--shadow)]", className)}>
      {rows.map((r) => (
        <div key={r.id} data-row={r.group} className="flex items-baseline gap-1.5">
          <span className="w-10 shrink-0 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{r.group === "pages" ? "Pages" : "Links"}</span>
          <span className="min-w-0">{r.label}</span>
        </div>
      ))}
    </div>
  );
}
