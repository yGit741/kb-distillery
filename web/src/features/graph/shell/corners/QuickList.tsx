import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { BUTTON, EDGE } from "./geometry";

/** One row of a corner's quick list: a chat or a note. */
export interface QuickRow {
  key: string;
  title: string;
  /** the age, or the chat's state ("running"), on the right */
  meta?: string;
  /** a chat that is working right now: its spark is green */
  running?: boolean;
}

interface Props {
  /** which corner: the chat list grows up from the bottom-left button, the Think list down from the top-right one */
  corner: "bottom-left" | "top-right";
  label: string;
  placeholder: string;
  /** every row, newest first; the four newest show while nothing is typed */
  rows: readonly QuickRow[];
  /** the small mark at the start of each row */
  icon: (row: QuickRow) => ReactNode;
  onPick: (key: string) => void;
  /** Enter on a line that picks no row: a new chat or a new thought with this text */
  onSubmit: (text: string) => void;
  onClose: () => void;
}

const RECENT = 4;
/** while typing, at most this many matches show */
const MATCHES = 6;
export const QUICK_ROW_H = 28;
export const QUICK_W = 300;
const GAP = 6;

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Flag graph-corners: the list a corner opens. Its first line takes the cursor at once ("Ask something new, or
 * find a chat"); the four newest rows sit beside it, nearest first. Typing filters every row; Enter starts a new one
 * with what was typed, or opens the row the arrows picked; Esc closes. Every row is 28px tall and 300px long,
 * starting at the button's own edge, and the list never moves anything on the graph.
 */
export function QuickList({ corner, label, placeholder, rows, icon, onPick, onSubmit, onClose }: Props) {
  const [text, setText] = useState("");
  // -1 = the line itself; 0.. = a row, counted away from the line
  const [pick, setPick] = useState(-1);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus({ preventScroll: true }), []);
  const q = text.trim().toLowerCase();
  const shown = useMemo(() => (q ? rows.filter((r) => r.title.toLowerCase().includes(q)).slice(0, MATCHES) : rows.slice(0, RECENT)), [rows, q]);
  useEffect(() => setPick(-1), [q]);
  const up = corner === "bottom-left";
  // the rows run away from the button: up from the spark, down from the brain
  const away = up ? "ArrowUp" : "ArrowDown";
  const back = up ? "ArrowDown" : "ArrowUp";

  const row = (r: QuickRow, i: number) => (
    <li key={r.key}>
      <button
        type="button"
        role="option"
        aria-selected={pick === i}
        data-quick-row={r.key}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => onPick(r.key)}
        className={cn(
          "pointer-events-auto flex w-full items-center gap-2 rounded-full border bg-card px-3 text-left text-[12.5px] shadow-[var(--shadow)] transition-colors hover:bg-accent motion-reduce:transition-none",
          pick === i && "bg-accent",
          RING,
        )}
        style={{ height: QUICK_ROW_H }}
      >
        <span aria-hidden className={cn("grid size-3.5 flex-none place-items-center", r.running ? "text-ok" : "text-muted-foreground")}>
          {icon(r)}
        </span>
        <span className="min-w-0 flex-1 truncate">{r.title}</span>
        {r.meta && <small className="flex-none text-[11px] text-muted-foreground">{r.meta}</small>}
      </button>
    </li>
  );

  const line = (
    <li key="line">
      <input
        ref={input}
        role="combobox"
        aria-expanded
        aria-label={placeholder}
        value={text}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onClose();
          } else if (e.key === away) {
            e.preventDefault();
            setPick((p) => Math.min(p + 1, shown.length - 1));
          } else if (e.key === back) {
            e.preventDefault();
            setPick((p) => Math.max(p - 1, -1));
          } else if (e.key === "Enter") {
            e.preventDefault();
            const r = pick >= 0 ? shown[pick] : undefined;
            if (r) onPick(r.key);
            else if (text.trim()) onSubmit(text.trim());
          }
        }}
        className={cn(
          "pointer-events-auto w-full rounded-full border bg-card px-3 text-[12.5px] shadow-[var(--shadow)] outline-none placeholder:text-muted-foreground focus:border-ring",
        )}
        style={{ height: QUICK_ROW_H }}
      />
    </li>
  );

  // nearest first: the newest row sits next to the line, older ones further away
  const list = shown.map(row);
  return (
    <ul
      role="listbox"
      aria-label={label}
      data-quick={corner}
      className="pointer-events-none absolute z-[26] flex flex-col"
      style={{
        width: QUICK_W,
        gap: GAP,
        ...(up
          ? { left: EDGE + 5, bottom: EDGE + BUTTON + 8, flexDirection: "column-reverse" }
          : { right: EDGE + 5, top: EDGE + BUTTON + 8 }),
      }}
    >
      {line}
      {list}
    </ul>
  );
}
