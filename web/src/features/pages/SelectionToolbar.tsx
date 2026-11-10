import { Flag, MessageSquarePlus } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { blockIndexOf, type SelectionChip } from "./PageChat";

const GAP = 8;
const EDGE = 8;
type Box = { left: number; top: number; width: number; height: number };

/** The selection's box in the viewport; zeros where the engine cannot measure (tests). */
function boxOf(range: Range): Box {
  const r = range.getBoundingClientRect?.();
  return r ? { left: r.left, top: r.top, width: r.width, height: r.height } : { left: 0, top: 0, width: 0, height: 0 };
}

/**
 * Where the toolbar goes: centred under the selection (never over the heading or line above it), flipped above only
 * when there is no room below, and kept inside the viewport horizontally. `null` when the selection is scrolled away.
 */
export function placeToolbar(sel: Box, size: { w: number; h: number }, view: { w: number; h: number }): { left: number; top: number } | null {
  const bottom = sel.top + sel.height;
  if (bottom < 0 || sel.top > view.h) return null;
  const left = Math.min(Math.max(sel.left + sel.width / 2 - size.w / 2, EDGE), Math.max(EDGE, view.w - size.w - EDGE));
  const below = bottom + GAP;
  const top = below + size.h + EDGE <= view.h ? below : Math.max(EDGE, sel.top - GAP - size.h);
  return { left, top };
}

type Held = { range: Range; chip: SelectionChip };

/**
 * A small toolbar next to the selected text: Ask about this (page chat) and Mark inaccurate (page flags, with an inline
 * note field: Enter saves, Escape cancels). Each action shows only when its handler is given.
 */
export function SelectionToolbar({
  articleRef,
  onAsk,
  onFlag,
}: {
  articleRef: RefObject<HTMLElement | null>;
  onAsk?: (c: SelectionChip) => void;
  onFlag?: (c: SelectionChip, note: string) => void;
}) {
  const [held, setHeld] = useState<Held | null>(null);
  const [noting, setNoting] = useState(false);
  const [note, setNote] = useState("");
  const [box, setBox] = useState<Box>({ left: 0, top: 0, width: 0, height: 0 });
  const [size, setSize] = useState({ w: 240, h: 32 });
  const ref = useRef<HTMLDivElement>(null);
  const notingRef = useRef(false);
  notingRef.current = noting;

  const close = useCallback(() => {
    setHeld(null);
    setNoting(false);
    setNote("");
  }, []);

  useEffect(() => {
    const onUp = (e: Event) => {
      if (notingRef.current || (e.target instanceof Node && ref.current?.contains(e.target))) return;
      const sel = window.getSelection();
      const text = sel?.toString().trim() ?? "";
      const root = articleRef.current;
      if (!sel || !text || !root || sel.rangeCount === 0 || !root.contains(sel.anchorNode)) {
        setHeld(null);
        return;
      }
      const range = sel.getRangeAt(0).cloneRange?.() ?? sel.getRangeAt(0);
      setHeld({ range, chip: { block_at: blockIndexOf(root, sel.anchorNode), text } });
      setBox(boxOf(range));
    };
    document.addEventListener("mouseup", onUp);
    document.addEventListener("keyup", onUp);
    return () => {
      document.removeEventListener("mouseup", onUp);
      document.removeEventListener("keyup", onUp);
    };
  }, [articleRef]);

  // stay attached to the words while the page scrolls or resizes
  useEffect(() => {
    if (!held) return;
    const again = () => setBox(boxOf(held.range));
    window.addEventListener("scroll", again, true);
    window.addEventListener("resize", again);
    return () => {
      window.removeEventListener("scroll", again, true);
      window.removeEventListener("resize", again);
    };
  }, [held]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (el && el.offsetHeight > 0 && (el.offsetWidth !== size.w || el.offsetHeight !== size.h)) setSize({ w: el.offsetWidth, h: el.offsetHeight });
  });

  if (!held) return null;
  const at = placeToolbar(box, size, { w: window.innerWidth, h: window.innerHeight });
  if (!at) return null;
  const btn = "inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs hover:bg-muted";
  return (
    <div
      ref={ref}
      role="toolbar"
      aria-label="Selection"
      className="fixed z-40 flex items-center gap-0.5 rounded-md border bg-card p-0.5 shadow-sm"
      style={{ left: at.left, top: at.top }}
    >
      {noting ? (
        <input
          autoFocus
          aria-label="What is inaccurate?"
          value={note}
          maxLength={500}
          placeholder="What is off? Enter to save"
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) {
              e.preventDefault();
              onFlag?.(held.chip, note.trim());
              window.getSelection()?.removeAllRanges();
              close();
            } else if (e.key === "Escape") close();
          }}
          className="w-64 bg-transparent px-2 py-1 text-xs outline-none"
        />
      ) : (
        <>
          {onAsk && (
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onAsk(held.chip);
                close();
              }}
              className={btn}
            >
              <MessageSquarePlus className="size-3.5" aria-hidden /> Ask about this
            </button>
          )}
          {onFlag && (
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => setNoting(true)} className={btn}>
              <Flag className="size-3.5" aria-hidden /> Mark inaccurate
            </button>
          )}
        </>
      )}
    </div>
  );
}
