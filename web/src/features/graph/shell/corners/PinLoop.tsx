import { useEffect, useRef, useState, type WheelEvent } from "react";
import { cn } from "@/lib/utils";
import { ago, type PinnedView } from "./api";
import { BUTTON, EDGE } from "./geometry";
import { useReducedMotion } from "./motion";
import { ViewThumb } from "./Thumb";

/** A card of the loop: the picture is 188 x 106; the next card starts this far below the last. */
export const LOOP_W = 188;
export const LOOP_H = 106;
export const LOOP_STEP = 54;
/** the top of the first card, under the pin */
export const LOOP_TOP = EDGE + BUTTON - 6;
/** room kept free above the bottom-left spark (its button and a gap), so the pile never runs into the chat list */
const KEEP_BOTTOM = EDGE + BUTTON + 24;

/** How many cards fit between the pin and the spark: a short window shows fewer, never fewer than one. */
export function loopFits(areaHeight: number): number {
  const free = areaHeight - LOOP_TOP - KEEP_BOTTOM - LOOP_H;
  return Math.max(1, Math.floor(free / LOOP_STEP) + 1);
}

interface Props {
  open: boolean;
  /** the pinned views, oldest first as the server lists them */
  views: readonly PinnedView[];
  /** the pinned view on screen: a small blue dot and a blue name */
  active: string | null;
  areaHeight: number;
  onApply: (id: string) => void;
  /** said when nothing is pinned yet */
  empty: string;
}

/**
 * Flag graph-corners: the pinned views hang from the pin in a vertical loop, partly overlapped and curving gently
 * into the border: the top card is in front, each one below peeks out with its name. The pin holds the pile and
 * never moves; the cards are what moves. Both ends of the pile fade into the border (the card before the front one
 * as a sheet tucked behind it, the last one at the bottom): clicking a faded one, or the wheel, turns the loop. Hover outlines a card and shows its
 * details; the view on screen has a small blue dot and a blue name. Pinning the current view is a command of the
 * search line (/pin), so the pile holds only what was pinned.
 */
export function PinLoop({ open, views, active, areaHeight, onApply, empty }: Props) {
  const still = useReducedMotion();
  const list = [...views].reverse(); // newest first
  const n = list.length;
  const fits = Math.min(n, loopFits(areaHeight));
  const looping = n > fits;
  const [turn, setTurn] = useState(0);
  useEffect(() => setTurn(0), [n]);
  const box = useRef<HTMLDivElement>(null);
  const wheelAt = useRef(0);
  const spin = (d: number) => looping && setTurn((t) => (((t + d) % n) + n) % n);
  const onWheel = (e: WheelEvent) => {
    if (!looping || Math.abs(e.deltaY) < 4) return;
    const now = performance.now();
    if (now - wheelAt.current < 160) return; // one card per notch, however fast the wheel spins
    wheelAt.current = now;
    spin(e.deltaY > 0 ? 1 : -1);
  };

  if (!n)
    return open ? (
      <p
        role="status"
        className="pointer-events-auto absolute z-[16] w-[240px] rounded-xl border bg-card px-3 py-2 text-[12.5px] text-muted-foreground shadow-[var(--shadow)]"
        style={{ left: EDGE + 5, top: LOOP_TOP + 12 }}
      >
        {empty}
      </p>
    ) : null;

  // slot 0 is the front card; with a loop the last slot is faded, and the card before the front one waits as a
  // faded sheet behind it: both turn the loop when pressed
  const slots = Array.from({ length: fits }, (_, s) => list[(s + turn) % n]!);
  const before = looping ? list[(turn - 1 + n) % n]! : null;
  const mid = (fits - 1) / 2;
  return (
    <div
      ref={box}
      role="list"
      aria-label="Pinned views"
      aria-hidden={!open}
      inert={!open}
      data-corners="pin-loop"
      onWheel={onWheel}
      className={cn("pointer-events-none absolute z-[16] transition-opacity duration-300 motion-reduce:transition-none", open ? "opacity-100" : "opacity-0")}
      style={{ left: EDGE + 4, top: LOOP_TOP, width: LOOP_W + 40, height: LOOP_H + (fits - 1) * LOOP_STEP }}
    >
      {before && (
        <button
          type="button"
          data-end="before"
          aria-label={`${before.name}, turn the pile back`}
          title={`Turn the pile back to ${before.name}`}
          onClick={() => spin(-1)}
          className="pointer-events-auto absolute left-0 rounded-[11px] border bg-card shadow-[var(--shadow)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          style={{ top: -10, width: LOOP_W, height: 40, zIndex: 0, opacity: 0.45, transform: "translateX(-6px) rotate(-5deg)", transformOrigin: "0 0" }}
        />
      )}
      {slots.map((v, s) => {
        // with a single card on screen it stays the one to press; the sheet behind it and the wheel turn the pile
        const end = looping && fits > 1 && s === fits - 1;
        // a gentle curve into the border: the middle card stands furthest out, the ends lean back toward the edge
        const k = fits > 1 ? (s - mid) / Math.max(1, mid) : 0;
        const x = Math.round(14 * (1 - k * k));
        const deg = fits > 1 ? -2.2 * k : 0;
        const on = v.id === active;
        return (
          <div
            key={v.id}
            role="listitem"
            className="absolute left-0"
            style={{
              top: s * LOOP_STEP,
              // the top card in front: each card below is behind the one above it and shows its name strip
              zIndex: fits - s + 1,
              transform: `translateX(${x}px) rotate(${deg}deg)`,
              transition: still ? undefined : "top .45s cubic-bezier(.32,.72,0,1), transform .45s cubic-bezier(.32,.72,0,1), opacity .28s",
              opacity: end ? 0.45 : 1,
            }}
          >
            <button
              type="button"
              data-view={v.id}
              data-end={end || undefined}
              aria-current={on || undefined}
              aria-label={end ? `${v.name}, turn the pile` : v.name}
              title={end ? `Turn the pile to ${v.name}` : `${v.name}, pinned ${ago(v.created)}`}
              onClick={() => (end ? spin(1) : onApply(v.id))}
              className={cn(
                "group pointer-events-auto relative block overflow-hidden rounded-[11px] border bg-card text-left shadow-[var(--shadow)] transition-[border-color,box-shadow] duration-150 motion-reduce:transition-none",
                "hover:border-primary hover:ring-2 hover:ring-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
              style={{ width: LOOP_W, height: LOOP_H }}
            >
              <ViewThumb id={v.id} className="absolute inset-0 size-full" />
              <span className="absolute inset-x-0 bottom-0 flex items-baseline gap-2 border-t bg-card px-2.5 py-1.5 text-[12.5px]">
                {on && <span aria-hidden className="size-1.5 flex-none self-center rounded-full bg-primary" />}
                <span className={cn("min-w-0 truncate font-semibold", on && "text-primary")}>{v.name}</span>
                <small className="ml-auto flex-none text-[11px] text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                  {ago(v.created)}
                </small>
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
