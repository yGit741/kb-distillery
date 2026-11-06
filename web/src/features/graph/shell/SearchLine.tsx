import type { KeyboardEvent, RefObject } from "react";
import { optionId, SearchPanel, type PanelRow } from "./SearchPanel";
import { SearchBar } from "./SearchBar";

interface Props {
  /** "graph": the line sits in the graph's own frame; "overlay": it is centred in a sheet on another screen. */
  context: "graph" | "overlay";
  value: string;
  onChange: (v: string) => void;
  rows: readonly PanelRow[];
  idx: number;
  setIdx: (i: number) => void;
  placeholder: string;
  empty: string;
  hint?: string;
  inputRef: RefObject<HTMLInputElement | null>;
  /** Escape. */
  onClose: () => void;
  /** Opens the action menu of row `i` (the trailing control, or the right arrow key). */
  onMenu?: (i: number, at: HTMLElement) => void;
}

/**
 * The search bar and its panel with the keys that drive them (arrows, Enter, Shift+Enter, the right arrow for a row's
 * menu, Escape). The overlay on every other screen renders this; the rows come from the caller.
 */
export function SearchLine({ context, value, onChange, rows, idx, setIdx, placeholder, empty, hint, inputRef, onClose, onMenu }: Props) {
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const n = rows.length;
      if (n) setIdx(e.key === "ArrowDown" ? (idx + 1) % n : (idx - 1 + n) % n);
    } else if (e.key === "ArrowRight" && onMenu) {
      const at = document.getElementById(optionId(idx));
      const t = e.currentTarget;
      if (rows[idx]?.actions && at && t.selectionStart === t.value.length && t.selectionEnd === t.value.length) {
        e.preventDefault();
        onMenu(idx, at);
      }
    } else if (e.key === "Enter") {
      if (e.nativeEvent.isComposing) return;
      e.preventDefault();
      rows[idx]?.run(e.shiftKey);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    }
  };
  return (
    <div data-context={context} className="w-full">
      <SearchBar value={value} onChange={onChange} open onOpen={() => {}} onKeyDown={onKeyDown} activeId={rows.length ? optionId(idx) : undefined} inputRef={inputRef} placeholder={placeholder} />
      <SearchPanel rows={rows} idx={idx} onHover={setIdx} empty={empty} hint={hint} onMenu={onMenu} />
    </div>
  );
}
