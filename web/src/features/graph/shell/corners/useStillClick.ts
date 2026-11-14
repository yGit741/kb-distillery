import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";

/** How far the pointer may drift between two clicks and still count as "the same spot". */
export const STILL_PX = 4;

/**
 * The click rule every legend shares. The click that opens a legend is remembered; a second click before the
 * pointer has moved more than `STILL_PX` away (no time limit) closes the legend again, whatever now sits under the
 * pointer. Once the pointer has moved, a click belongs to the row under it. So two clicks on the same spot always
 * open and close, and they never reach a row that slid under the pointer when the legend opened.
 *
 * `mark` goes on the opener's click, `onClickCapture` on the legend's box. Keyboard presses (no pointer position)
 * are never still clicks. `settled` is false from the opening click until the pointer moves away: until then nothing
 * under the pointer may look chosen (no hover tint, no spotlight), since the row only slid there.
 *
 * `markUndo` goes on a row's own click inside an open legend: a second click on the same spot then reads as a double
 * click on that row. It undoes what the first click did and closes the legend, so a double click never leaves a
 * change behind.
 */
export function useStillClick(open: boolean, close: () => void) {
  const at = useRef<{ x: number; y: number } | null>(null);
  const undo = useRef<{ back: () => void; row: EventTarget } | null>(null);
  const [settled, setSettled] = useState(true);
  useEffect(() => {
    if (!open) {
      at.current = null;
      undo.current = null;
      setSettled(true);
      return;
    }
    const move = (e: PointerEvent | MouseEvent) => {
      const p = at.current;
      if (p && Math.hypot(e.clientX - p.x, e.clientY - p.y) > STILL_PX) {
        at.current = null;
        undo.current = null;
        setSettled(true);
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("mousemove", move);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("mousemove", move);
    };
  }, [open]);
  return {
    settled,
    mark: (e: ReactMouseEvent) => {
      at.current = e.detail === 0 ? null : { x: e.clientX, y: e.clientY };
      undo.current = null;
      setSettled(!at.current);
    },
    /** a row's click in the open legend: remember how to take it back if the next click lands on the same spot */
    markUndo: (e: ReactMouseEvent, back: () => void) => {
      at.current = e.detail === 0 ? null : { x: e.clientX, y: e.clientY };
      undo.current = at.current ? { back, row: e.currentTarget } : null;
    },
    onClickCapture: (e: ReactMouseEvent) => {
      const p = at.current;
      if (!open || !p || e.detail === 0) return;
      if (Math.hypot(e.clientX - p.x, e.clientY - p.y) > STILL_PX) return;
      const u = undo.current;
      // after a row's click, only a second click on that same row is a double click
      if (u && !(e.target instanceof Node && u.row instanceof Node && u.row.contains(e.target))) {
        at.current = null;
        undo.current = null;
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      at.current = null;
      undo.current = null;
      setSettled(true);
      u?.back();
      close();
    },
  };
}
