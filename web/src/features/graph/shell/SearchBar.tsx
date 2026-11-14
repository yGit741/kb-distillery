import { useState, type KeyboardEvent, type RefObject } from "react";
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
  /** The input's placeholder (copy.ts when graph-intent is on). */
  placeholder: string;
  /** A quiet one-line notice shown in place of the placeholder for a moment. */
  notice?: string;
  /** Key caps shown at the right end while the line has the focus and is empty; they fade out on typing. */
  keys?: readonly { key: string; label: string }[];
  /** The side where the Concepts / Sources switch meets the line: those corners lose their rounding. */
  square?: "left" | null;
}

/**
 * The search bar at top centre: just the input, no icons or shortcut hint (the knowledge base switcher is the
 * app bar's badge, or "/knowledge" here). It is the combobox; the panel under it (SearchPanel) is its listbox.
 * At rest it only invites; on focus the `keys` appear at its right end and fade once something is typed.
 */
export function SearchBar({ value, onChange, open, onOpen, onKeyDown, activeId, inputRef, placeholder, notice, square, keys }: Props) {
  const [focused, setFocused] = useState(false);
  const showKeys = focused && !value && !notice;
  return (
    <div
      className={cn(
        // a size container: the key caps leave when the line itself is narrow (a side panel open), not only the window
        "@container flex h-11 items-center gap-2.5 rounded-[14px] border bg-card px-3.5 text-sm shadow-[var(--shadow)]",
        "transition-[border-color,box-shadow] duration-200 motion-reduce:transition-none",
        "focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/25",
        square === "left" && "rounded-l-none",
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
        aria-description={keys?.length ? keys.map((k) => `Type ${k.key} for ${k.label}`).join(", ") : undefined}
        type="text"
        autoComplete="off"
        spellCheck={false}
        placeholder={notice ?? placeholder}
        className="min-h-6 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => {
          setFocused(true);
          onOpen();
        }}
        onBlur={() => setFocused(false)}
        onClick={onOpen}
        onKeyDown={onKeyDown}
      />
      {keys && keys.length > 0 && (
        <span
          aria-hidden
          data-testid="line-keys"
          data-shown={showKeys || undefined}
          className={cn("flex flex-none items-center gap-3 whitespace-nowrap text-xs text-muted-foreground transition-opacity duration-150 motion-reduce:transition-none @max-[360px]:hidden", showKeys ? "opacity-100" : "pointer-events-none opacity-0")}
        >
          {keys.map((k) => (
            <span key={k.key} className="flex items-center gap-1.5">
              <kbd className="grid h-[18px] min-w-[18px] place-items-center rounded-[5px] border bg-background px-1 font-mono text-[11px] leading-none text-foreground">{k.key}</kbd>
              {k.label}
            </span>
          ))}
        </span>
      )}
      <span role="status" className="sr-only">
        {notice}
      </span>
    </div>
  );
}
