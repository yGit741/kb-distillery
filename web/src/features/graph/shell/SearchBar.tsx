import type { KeyboardEvent, RefObject } from "react";
import { cn } from "@/lib/utils";

export const SHELL_SEARCH_ID = "graph-shell-search";
export const SHELL_LIST_ID = "graph-shell-list";

interface Props {
  value: string;
  onChange: (v: string) => void;
  open: boolean;
  onOpen: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  /** The id of the highlighted option (aria-activedescendant). */
  activeId?: string;
  inputRef: RefObject<HTMLInputElement | null>;
  /** The knowledge base the graph shows, named in the placeholder. */
  kbName: string;
  /** A quiet one-line notice shown in place of the placeholder for a moment. */
  notice?: string;
}

/**
 * The search bar at top centre: just the input, no icons or shortcut hint (the knowledge base switcher is the
 * app bar's badge, or "/knowledge" here). It is the combobox; the panel under it (SearchPanel) is its listbox.
 */
export function SearchBar({ value, onChange, open, onOpen, onKeyDown, activeId, inputRef, kbName, notice }: Props) {
  return (
    <div
      className={cn(
        "flex h-11 items-center gap-2.5 rounded-[14px] border bg-card px-3.5 text-sm shadow-[var(--shadow)]",
        "transition-[border-color,box-shadow] duration-200 motion-reduce:transition-none",
        "focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/25",
      )}
    >
      <input
        ref={inputRef}
        id={SHELL_SEARCH_ID}
        data-tour="graph-search"
        role="combobox"
        aria-expanded={open}
        aria-controls={open ? SHELL_LIST_ID : undefined}
        aria-autocomplete="list"
        aria-activedescendant={open ? activeId : undefined}
        aria-label="Search the graph, run a command (/), or ask"
        type="text"
        autoComplete="off"
        spellCheck={false}
        placeholder={notice ?? `Search ${kbName}`}
        className="min-h-6 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onOpen}
        onClick={onOpen}
        onKeyDown={onKeyDown}
      />
      <span role="status" className="sr-only">
        {notice}
      </span>
    </div>
  );
}
