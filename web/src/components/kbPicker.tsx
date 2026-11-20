import { Search, Star } from "lucide-react";
import { Input } from "@/components/ui/input";
import { kbProblem, sizeTitle, type KbSize } from "@/lib/kbSize";
import { cn } from "@/lib/utils";

/** The search line of a knowledge base list; Enter calls `onEnter` (open the first match). */
export function KbSearch({ value, onChange, onEnter, autoFocus, className }: {
  value: string;
  onChange: (v: string) => void;
  onEnter?: () => void;
  autoFocus?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <Search aria-hidden className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input
        type="search"
        aria-label="Search knowledge bases"
        placeholder="Search knowledge bases…"
        autoComplete="off"
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && onEnter) {
            e.preventDefault();
            onEnter();
          }
        }}
        className="h-8 pl-7"
      />
    </div>
  );
}

/** A knowledge base's graph size in small print (concepts · sources · edges), red with the reason when unhealthy. */
export function KbSizeChip({ size }: { size: KbSize | undefined }) {
  if (!size) return null;
  const problem = kbProblem(size);
  return (
    <span
      data-testid="kb-size"
      title={problem ? `${sizeTitle(size)} — ${problem}` : sizeTitle(size)}
      className={cn("shrink-0 text-[11px] tabular-nums", problem ? "font-medium text-destructive" : "text-muted-foreground")}
    >
      {size.concepts}c · {size.sources}s · {size.edges}e
    </span>
  );
}

/** The star beside a knowledge base: a toggle button, filled when starred. */
export function StarToggle({ name, on, onToggle, className }: { name: string; on: boolean; onToggle: () => void; className?: string }) {
  return (
    <button
      type="button"
      aria-label={`Star ${name}`}
      aria-pressed={on}
      title={on ? "Starred: kept at the top. Click to unstar" : "Star: keep it at the top"}
      onClick={onToggle}
      className={cn(
        "grid size-5 shrink-0 place-items-center rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        on ? "text-amber-500" : "text-muted-foreground/50 hover:text-foreground",
        className,
      )}
    >
      <Star aria-hidden className="size-3.5" strokeWidth={1.8} fill={on ? "currentColor" : "none"} />
    </button>
  );
}

/** The menu rows split into the starred group, a divider and the rest; `empty` when nothing matches. */
export function StarredRows<T>({ starred, rest, row, empty }: { starred: T[]; rest: T[]; row: (r: T) => React.ReactNode; empty?: React.ReactNode }) {
  return (
    <div className="max-h-[55vh] overflow-y-auto">
      {starred.length > 0 && (
        <div role="group" aria-label="Starred">
          <p className="px-1.5 pb-0.5 pt-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Starred</p>
          {starred.map(row)}
        </div>
      )}
      {starred.length > 0 && rest.length > 0 && <div className="mx-1.5 my-1 border-t" />}
      {rest.map(row)}
      {!starred.length && !rest.length && empty}
    </div>
  );
}
