import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { SHELL_LIST_ID } from "./SearchBar";

export interface PanelRow {
  key: string;
  section: string;
  label: ReactNode;
  /** A second quiet line (a snippet). */
  detail?: string;
  /** A quiet word at the right. */
  hint?: string;
  lead?: ReactNode;
  run: (shift: boolean) => void;
}

export const optionId = (i: number) => `${SHELL_LIST_ID}-opt-${i}`;

interface Props {
  rows: readonly PanelRow[];
  idx: number;
  onHover: (i: number) => void;
  /** Shown when there are no rows. */
  empty: string;
}

/** The unfolded panel: rows in labelled sections, one highlighted, scrolling past a maximum height. */
export function SearchPanel({ rows, idx, onHover, empty }: Props) {
  const groups: { section: string; items: { row: PanelRow; i: number }[] }[] = [];
  rows.forEach((row, i) => {
    const last = groups[groups.length - 1];
    if (last && last.section === row.section) last.items.push({ row, i });
    else groups.push({ section: row.section, items: [{ row, i }] });
  });
  return (
    <div
      id={SHELL_LIST_ID}
      role="listbox"
      aria-label="Search results and commands"
      className="mt-1.5 max-h-[min(65vh,30rem)] overflow-y-auto overscroll-contain rounded-[14px] border bg-popover p-2 text-sm shadow-[var(--shadow)]"
      // keep focus in the input while the pointer works the list
      onMouseDown={(e) => e.preventDefault()}
    >
      {groups.map((g, gi) => (
        <div key={`${g.section}:${gi}`} role="group" aria-labelledby={`${SHELL_LIST_ID}-h${gi}`}>
          <div id={`${SHELL_LIST_ID}-h${gi}`} className="px-2.5 pb-1 pt-3 text-xs font-medium text-muted-foreground first:pt-0.5">
            {g.section}
          </div>
          {g.items.map(({ row, i }) => (
            <div
              key={row.key}
              id={optionId(i)}
              role="option"
              aria-selected={i === idx}
              ref={(el) => {
                if (el && i === idx) el.scrollIntoView?.({ block: "nearest" });
              }}
              className={cn("flex min-h-9 cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-1.5", i === idx && "bg-accent")}
              onMouseMove={() => i !== idx && onHover(i)}
              onClick={(e) => row.run(e.shiftKey)}
            >
              {row.lead && <span className="grid size-4 shrink-0 place-items-center text-muted-foreground [&>svg]:size-4 [&>svg]:stroke-[1.6]">{row.lead}</span>}
              <span className="min-w-0 flex-1">
                <span className="block truncate">{row.label}</span>
                {row.detail && <span className="block truncate text-xs text-muted-foreground">{row.detail}</span>}
              </span>
              {row.hint && <span className="max-w-[45%] shrink-0 truncate text-xs text-muted-foreground">{row.hint}</span>}
            </div>
          ))}
        </div>
      ))}
      {!rows.length && <div className="px-2.5 py-2 text-muted-foreground">{empty}</div>}
    </div>
  );
}
