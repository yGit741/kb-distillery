import { Database, Search } from "lucide-react";
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
  /** The knowledge base the graph shows: the tooltip of the icon at the left. */
  kbName: string;
  /** A quiet one-line notice shown in place of the placeholder for a moment. */
  notice?: string;
  onKbClick: () => void;
}

/**
 * The search bar at top centre: the knowledge base icon (kept visible), a hairline, the input and the
 * shortcut hint. It is the combobox; the panel under it (SearchPanel) is its listbox.
 */
export function SearchBar({ value, onChange, open, onOpen, onKeyDown, activeId, inputRef, kbName, notice, onKbClick }: Props) {
  return (
    <div
      className={cn(
        "flex h-11 items-center gap-2.5 rounded-[14px] border bg-card px-3.5 text-sm shadow-[var(--shadow)]",
        "transition-[border-color,box-shadow] duration-200 motion-reduce:transition-none",
        "focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/25",
      )}
    >
      <button
        type="button"
        aria-label={`Knowledge base: ${kbName}`}
        title={kbName}
        onClick={onKbClick}
        className="-ml-1.5 grid size-7 shrink-0 place-items-center rounded-lg text-foreground outline-offset-0 transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring motion-reduce:transition-none"
      >
        <Database aria-hidden className="size-[18px]" strokeWidth={1.6} />
      </button>
      <span aria-hidden className="h-5 w-px shrink-0 bg-border" />
      <Search aria-hidden className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.6} />
      <input
        ref={inputRef}
        id={SHELL_SEARCH_ID}
        data-tour="graph-search"
        role="combobox"
        aria-expanded={open}
        aria-controls={SHELL_LIST_ID}
        aria-autocomplete="list"
        aria-activedescendant={open ? activeId : undefined}
        aria-label="Search the graph, run a command (/), or ask"
        type="text"
        autoComplete="off"
        spellCheck={false}
        placeholder={notice ?? `Search ${kbName}`}
        className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onOpen}
        onClick={onOpen}
        onKeyDown={onKeyDown}
      />
      {!open && !value && !notice && (
        <kbd aria-hidden className="shrink-0 rounded-[5px] border px-1.5 text-[11px] leading-5 text-muted-foreground">
          ⌘K
        </kbd>
      )}
      <span role="status" className="sr-only">
        {notice}
      </span>
    </div>
  );
}
