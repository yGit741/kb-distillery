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
 */
export function useStillClick(open: boolean, close: () => void) {
  const at = useRef<{ x: number; y: number } | null>(null);
  const [settled, setSettled] = useState(true);
  useEffect(() => {
    if (!open) {
      at.current = null;
      setSettled(true);
      return;
    }
    const move = (e: PointerEvent | MouseEvent) => {
      const p = at.current;
      if (p && Math.hypot(e.clientX - p.x, e.clientY - p.y) > STILL_PX) {
        at.current = null;
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
      setSettled(!at.current);
    },
    onClickCapture: (e: ReactMouseEvent) => {
      const p = at.current;
      if (!open || !p || e.detail === 0) return;
      if (Math.hypot(e.clientX - p.x, e.clientY - p.y) > STILL_PX) return;
      e.preventDefault();
      e.stopPropagation();
      at.current = null;
      setSettled(true);
      close();
    },
  };
}
