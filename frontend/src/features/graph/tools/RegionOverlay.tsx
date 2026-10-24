import { useEffect, useRef, useState } from "react";
import { DRAG_PX, MIN_LASSO_POINTS, pickInRegion, type Pt, type Region } from "../selection";
import type { GraphToolContext } from ".";

const SCREEN = '[data-testid="graph-screen"]';
/** A left press this close (px) to a page grabs the page, not the background. */
const NODE_PX = 10;

/**
 * Left-drag on empty canvas (or right-drag anywhere): a box selects what it covers (Shift adds to the
 * selection), Cmd/Ctrl+drag draws a freeform lasso that adds. A left-drag that starts on a page moves the
 * page instead; a right-click without a drag stays the page menu (the canvas decides that on release).
 * Listeners are on the window and never capture the pointer, or force-graph would miss the pointerup and
 * stop reporting hovers.
 */
export function RegionOverlay({ ctx }: { ctx: GraphToolContext }) {
  const live = useRef(ctx);
  live.current = ctx;
  const [region, setRegion] = useState<Region | null>(null);

  useEffect(() => {
    const root = document.querySelector(SCREEN);
    if (!root) return;
    let drag: { id: number; start: Pt; lasso: boolean; additive: boolean; pts: Pt[]; moved: boolean } | null = null;
    const onPage = (at: Pt) => {
      const c = live.current;
      const near = { kind: "box" as const, a: { x: at.x - NODE_PX, y: at.y - NODE_PX }, b: { x: at.x + NODE_PX, y: at.y + NODE_PX } };
      return pickInRegion(near, c.visible, c.screenOf).length > 0;
    };
    const regionOf = (d: NonNullable<typeof drag>, to: Pt): Region => (d.lasso ? { kind: "lasso", pts: d.pts } : { kind: "box", a: d.start, b: to });

    const down = (e: Event) => {
      const p = e as PointerEvent;
      // only the canvas itself starts a gesture; the panels and buttons float above it
      if ((p.button !== 0 && p.button !== 2) || !(p.target instanceof HTMLCanvasElement)) return;
      const start = { x: p.clientX, y: p.clientY };
      if (p.button === 0 && onPage(start)) return;
      drag = { id: p.pointerId, start, lasso: p.metaKey || p.ctrlKey, additive: p.shiftKey, pts: [start], moved: false };
    };
    const move = (e: PointerEvent) => {
      if (!drag || e.pointerId !== drag.id) return;
      const at = { x: e.clientX, y: e.clientY };
      if (!drag.moved) {
        if (Math.hypot(at.x - drag.start.x, at.y - drag.start.y) < DRAG_PX) return;
        drag.moved = true;
      }
      if (drag.lasso) drag.pts = [...drag.pts, at];
      setRegion(regionOf(drag, at));
    };
    const finish = (e: PointerEvent) => {
      if (!drag || e.pointerId !== drag.id) return;
      const d = drag;
      drag = null;
      setRegion(null);
      if (e.type === "pointercancel" || !d.moved) return;
      const c = live.current;
      const r = regionOf(d, { x: e.clientX, y: e.clientY });
      const ids = pickInRegion(r, c.visible, c.screenOf);
      if (d.lasso) {
        if (ids.length && d.pts.length >= MIN_LASSO_POINTS) c.select(ids, { additive: true });
      } else if (ids.length) c.select(ids, { additive: d.additive });
      else if (!d.additive) c.clearSelection();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && drag) {
        drag = null;
        setRegion(null);
      }
    };
    root.addEventListener("pointerdown", down, true);
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", finish, true);
    window.addEventListener("pointercancel", finish, true);
    window.addEventListener("keydown", key, true);
    return () => {
      root.removeEventListener("pointerdown", down, true);
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", finish, true);
      window.removeEventListener("pointercancel", finish, true);
      window.removeEventListener("keydown", key, true);
    };
  }, []);

  if (!region) return null;
  if (region.kind === "box") {
    const x = Math.min(region.a.x, region.b.x);
    const y = Math.min(region.a.y, region.b.y);
    return (
      <div
        aria-hidden
        data-testid="region-box"
        className="pointer-events-none fixed z-40 rounded-sm border border-primary bg-primary/10"
        style={{ left: x, top: y, width: Math.abs(region.a.x - region.b.x), height: Math.abs(region.a.y - region.b.y) }}
      />
    );
  }
  return (
    <svg aria-hidden data-testid="region-lasso" className="pointer-events-none fixed inset-0 z-40 size-full text-primary">
      <polygon points={region.pts.map((p) => `${p.x},${p.y}`).join(" ")} className="fill-primary/10 stroke-primary" strokeWidth={1.5} strokeDasharray="6 4" />
    </svg>
  );
}
