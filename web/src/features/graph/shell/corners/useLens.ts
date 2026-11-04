import { useCallback, useEffect, useRef, type RefObject } from "react";
import { bowOffset, lensHover, lensLayout, lensTops, type LensItem } from "./geometry";

export interface LensRow extends LensItem {
  key: string;
}

interface Cur {
  x: number;
  s: number;
  o: number;
  dy: number;
}

/**
 * The Dock lens of the pinned-views list. The hovered row grows, its neighbours less, the grown rows push the
 * others apart so they never overlap; every row also bows right at the middle of the visible height (the ")"
 * curve). The pointer is released the moment it leaves the list, the window or the tab. Transforms are written
 * straight to the row elements (no React render per frame) and eased towards their targets.
 */
export function useLens(lens: RefObject<HTMLElement | null>, rows: readonly LensRow[], els: RefObject<Map<string, HTMLElement>>) {
  const pointer = useRef<number | null>(null);
  const hover = useRef(-1);
  const cur = useRef(new Map<string, Cur>());
  const raf = useRef(0);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const reduced = useRef(false);

  const frame = useCallback(() => {
    raf.current = 0;
    const box = lens.current;
    if (!box) return;
    const items = rowsRef.current;
    const tops = lensTops(items);
    const h = box.clientHeight || 1;
    const rect = box.getBoundingClientRect();
    const mid = rect.top + h / 2;
    const st = box.scrollTop;
    hover.current = pointer.current === null ? -1 : lensHover(items, tops, pointer.current - rect.top + st, hover.current);
    const tg = lensLayout(items, hover.current, st);
    let moving = false;
    items.forEach((it, i) => {
      const el = els.current?.get(it.key);
      const t = tg[i]!;
      if (!el) return;
      const sy = rect.top + tops[i]! + it.hb / 2 + t.dy - st;
      const d = Math.max(-1.3, Math.min(1.3, (sy - mid) / (h / 2)));
      const goal = { x: bowOffset(d), s: t.s, o: 1, dy: t.dy };
      const k = cur.current.get(it.key) ?? { x: goal.x, s: 0.6, o: 0, dy: goal.dy - 8 * i };
      for (const q of ["x", "s", "o", "dy"] as const) {
        const dv = goal[q] - k[q];
        k[q] = reduced.current ? goal[q] : k[q] + dv * 0.24;
        if (Math.abs(dv) > 0.01 && !reduced.current) moving = true;
      }
      cur.current.set(it.key, k);
      el.style.transform = `translate(${k.x.toFixed(2)}px, ${k.dy.toFixed(2)}px) scale(${k.s.toFixed(3)})`;
      el.style.opacity = k.o.toFixed(3);
      el.dataset.scale = k.s.toFixed(2);
      el.dataset.focus = t.g > 0.8 ? "true" : "false";
    });
    if (moving) raf.current = requestAnimationFrame(frame);
  }, [lens, els]);

  const kick = useCallback(() => {
    if (!raf.current) raf.current = requestAnimationFrame(frame);
  }, [frame]);

  const release = useCallback(() => {
    if (pointer.current === null) return;
    pointer.current = null;
    kick();
  }, [kick]);
  /** a focused row counts as the pointer being on it (keyboard users get the lens too) */
  const focusRow = useCallback(
    (key: string) => {
      const box = lens.current;
      const i = rowsRef.current.findIndex((r) => r.key === key);
      if (!box || i < 0) return;
      const tops = lensTops(rowsRef.current);
      pointer.current = box.getBoundingClientRect().top + tops[i]! + rowsRef.current[i]!.hb / 2 - box.scrollTop;
      kick();
    },
    [lens, kick],
  );

  useEffect(() => {
    reduced.current = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    // the list takes no pointer events itself (it would cover the graph); its rows do. The pointer drives the lens
    // while it is over a row and is released the moment it is anywhere else.
    const out = (e: Event) => {
      const t = e.target;
      const y = (e as MouseEvent).clientY;
      if (t instanceof Element && t.closest("[data-lens-row]")) {
        pointer.current = y;
        kick();
      } else release();
    };
    const leave = () => release();
    document.addEventListener("pointermove", out, { passive: true });
    document.documentElement.addEventListener("mouseleave", leave);
    window.addEventListener("blur", leave);
    document.addEventListener("visibilitychange", leave);
    const box = lens.current;
    box?.addEventListener("scroll", kick, { passive: true });
    window.addEventListener("resize", kick);
    return () => {
      document.removeEventListener("pointermove", out);
      document.documentElement.removeEventListener("mouseleave", leave);
      window.removeEventListener("blur", leave);
      document.removeEventListener("visibilitychange", leave);
      box?.removeEventListener("scroll", kick);
      window.removeEventListener("resize", kick);
      if (raf.current) cancelAnimationFrame(raf.current);
      raf.current = 0;
    };
  }, [lens, kick, release]);

  // rows came or went: lay them out again
  const sig = rows.map((r) => r.key).join("|");
  useEffect(() => {
    for (const k of [...cur.current.keys()]) if (!rows.some((r) => r.key === k)) cur.current.delete(k);
    kick();
  }, [sig, kick]); // eslint-disable-line react-hooks/exhaustive-deps

  return { release, focusRow, kick };
}
