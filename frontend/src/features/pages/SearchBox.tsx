import { useNavigate } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { forwardRef, useMemo, useState, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";
import { suggest, type LinkGraph } from "./lib";
import { PAGES_TO, TypeDot, pageTo } from "./parts";

interface Props {
  g?: LinkGraph;
  initial?: string;
}

/** Title suggestions as you type; Enter on "search inside all pages" runs the full-text search. */
export const SearchBox = forwardRef<HTMLInputElement, Props>(function SearchBox({ g, initial = "" }, ref) {
  const navigate = useNavigate();
  const [value, setValue] = useState(initial);
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const hits = useMemo(() => (g ? suggest(g, value) : []), [g, value]);
  const q = value.trim();
  const rows = q ? hits.length + 1 : 0; // last row = full-text search

  const go = (i: number) => {
    setOpen(false);
    if (i < hits.length) void navigate({ to: pageTo(hits[i]!.id) });
    else if (q) void navigate({ to: PAGES_TO, search: { q } as never });
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      if (rows) setIdx((idx + (e.key === "ArrowDown" ? 1 : -1) + rows) % rows);
    } else if (e.key === "Enter" && q) {
      e.preventDefault();
      go(Math.min(idx, rows - 1));
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative min-w-0 flex-1">
      <Search aria-hidden className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
      <input
        ref={ref}
        type="search"
        role="combobox"
        aria-expanded={open && rows > 0}
        aria-controls="pages-suggest"
        aria-label="Search pages"
        placeholder="Search pages…  ( / )"
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setIdx(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKey}
        className="h-9 w-full rounded-md border bg-transparent pl-8 pr-3 text-sm placeholder:text-muted-foreground"
      />
      {open && rows > 0 && (
        <div id="pages-suggest" role="listbox" className="absolute left-0 right-0 top-10 z-30 overflow-hidden rounded-md border bg-popover text-sm shadow-md">
          {hits.map((p, i) => (
            <button
              key={p.id}
              type="button"
              role="option"
              aria-selected={i === idx}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => go(i)}
              className={cn("flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-accent", i === idx && "bg-accent")}
            >
              <TypeDot type={p.type} />
              <span className="min-w-0 flex-1 truncate">{p.title}</span>
              <small className="text-xs text-muted-foreground">{p.type}</small>
            </button>
          ))}
          <button
            type="button"
            role="option"
            aria-selected={idx === hits.length}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => go(hits.length)}
            className={cn("w-full border-t px-3 py-1.5 text-left text-muted-foreground hover:bg-accent", idx === hits.length && "bg-accent")}
          >
            Search inside all pages for “{q}” ↵
          </button>
        </div>
      )}
    </div>
  );
});
