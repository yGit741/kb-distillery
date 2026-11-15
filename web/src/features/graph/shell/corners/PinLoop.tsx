import { useEffect, useMemo, useRef, useState, type WheelEvent } from "react";
import { cn } from "@/lib/utils";
import { ago, type PinnedView } from "./api";
import { BUTTON, EDGE } from "./geometry";
import { useReducedMotion } from "./motion";
import { GraphThumb, type ThumbKind } from "./Thumb";

/** A card of the loop: the picture is 188 x 106. */
export const LOOP_W = 188;
export const LOOP_H = 106;
/**
 * The loop hangs from the pin's centre (the Fan Design mockup): the top card's top-left corner sits exactly there, so
 * the pin's disc covers a quarter of it, and the cards turned past swing up about the same point.
 */
export const LOOP_TOP = EDGE + BUTTON / 2;
const LOOP_LEFT = EDGE + BUTTON / 2;
/** px between solid cards along the arc; the two fading cards after them sit closer (54, then 36) */
const STEP = 66;

/**
 * How many solid cards the loop shows (the Fan Design mockup): 5 in a tall window, 4 in a medium one, 3 in a short
 * one. The mockup measured the window (860 and 680px); the graph area is the window less the 48px app bar.
 */
export function loopSolid(areaHeight: number): number {
  return areaHeight >= 812 ? 5 : areaHeight >= 632 ? 4 : 3;
}

/**
 * Where each place of the loop sits: one gentle circular arc hanging from the pin and bending left, each card turned
 * a little more than the one above (rotation about its top-left corner). The bend is the one that brings the
 * bottom-left corner of the last solid card exactly onto the graph area's left border; the fading places carry on past it.
 */
export function arcPlaces(solid: number): { x: number; y: number; deg: number }[] {
  if (solid < 1) return [];
  // a single solid card has no last corner to bring to the border: give the arc a small fixed bend
  if (solid < 2) {
    const k = 0.06;
    return [0, 1, 2].map((j) => ({ x: -54 * Math.sin(k * j) * j, y: [0, 54, 90][j]!, deg: (k * j * 180) / Math.PI }));
  }
  const steps = [...Array(Math.max(0, solid - 1)).fill(STEP), 54, 36];
  const geo = (k: number) => {
    const a = Array.from({ length: solid + 2 }, (_, j) => k * j);
    const p: [number, number][] = [[0, 0]];
    for (let j = 0; j < solid + 1; j++) {
      const m = (a[j]! + a[j + 1]!) / 2;
      p.push([p[j]![0] - steps[j]! * Math.sin(m), p[j]![1] + steps[j]! * Math.cos(m)]);
    }
    return { a, p };
  };
  let lo = 0;
  let hi = 0.2;
  for (let it = 0; it < 32; it++) {
    const k = (lo + hi) / 2;
    const g = geo(k);
    const last = solid - 1;
    if (g.p[last]![0] - LOOP_H * Math.sin(g.a[last]!) > -(LOOP_LEFT + 2)) lo = k;
    else hi = k;
  }
  const g = geo((lo + hi) / 2);
  return g.p.map(([x, y], j) => ({ x, y, deg: (g.a[j]! * 180) / Math.PI }));
}

export type SlotName = "solid" | "b1" | "b2" | "t1" | "t2" | "t3";

/**
 * Which place each card takes, by its steps after the front one (null = out of sight). Up to the window's count every
 * card is solid. Past it both ends always show, as in the mockup: the next card half there below (b1) and the card
 * just turned past tilted above the pin (t1); with more cards, the one after almost gone below (b2), then two more
 * tilted above (t2, t3). The solid run gives way (never below two) so the ends fit.
 */
export function loopSlots(n: number, base: number): { solid: number; slots: (SlotName | null)[] } {
  if (n <= base) return { solid: n, slots: Array.from({ length: n }, (): SlotName => "solid") };
  const solid = Math.max(2, Math.min(base, n - 3));
  const slots: (SlotName | null)[] = Array.from({ length: n }, (_, j) => (j < solid ? "solid" : null));
  const free = (j: number) => j >= solid && j < n && slots[j] === null;
  const put = (j: number, name: SlotName) => free(j) && (slots[j] = name);
  put(solid, "b1");
  put(n - 1, "t1");
  put(solid + 1, "b2");
  // t2 and t3 only behind the cards already placed below, so the two ends never meet
  if (n - 2 > solid + 1) put(n - 2, "t2");
  if (n - 3 > solid + 1) put(n - 3, "t3");
  return { solid, slots };
}

/** A card of the loop that is not a pinned view: a view of the graph (Concepts …) or a view built on the embedding. */
export interface LoopCard {
  id: string;
  name: string;
  /** the small grey text after the name ("Embedding based") */
  meta?: string;
  hint?: string;
  /** the view on screen */
  on?: boolean;
  /** offered until pinned: a dashed, quieter card */
  suggested?: boolean;
  /** which picture the card shows */
  thumb?: ThumbKind;
}

interface Props {
  open: boolean;
  /** the pinned views, oldest first as the server lists them */
  views: readonly PinnedView[];
  /** cards before the pinned views (the graph's views) and after them (views built on the embedding) */
  lead?: readonly LoopCard[];
  tail?: readonly LoopCard[];
  /** a lead or tail card was pressed */
  onPick?: (id: string) => void;
  /** the pinned view on screen: a small blue dot and a blue name */
  active: string | null;
  areaHeight: number;
  onApply: (id: string) => void;
  /** said when nothing is pinned yet */
  empty: string;
}

type Item = { key: string; name: string; meta?: string; hint: string; on: boolean; suggested?: boolean; thumb?: ThumbKind; apply: () => void };

/** A place in the loop: a solid card, a fading one below (b1, b2), or one turned past, tilted above the pin (t1–t3). */
type Slot = { solid: boolean; end?: "b1" | "b2" | "t1" | "t2" | "t3"; x: number; y: number; deg: number; opacity: number; z: number };

/**
 * Flag graph-corners: the views hang from the pin in a loop, as in the Fan Design mockup (loop, curved, fading ends).
 * A few solid cards lie on one arc bending left, each partly over the one below; after them the next card is half
 * there and the one after almost gone; the cards you turned past stay tilted above the pin and fade toward the top
 * border. The pin never moves; the cards are what moves. A faded card or the wheel turns the loop. Closed, the cards
 * tuck behind the pin as a small pile. Hover outlines a card; the view on screen has a small blue dot and a blue name.
 * Pinning the current view is a command of the search line (/pin).
 */
export function PinLoop({ open, views, lead = [], tail = [], onPick, active, areaHeight, onApply, empty }: Props) {
  const still = useReducedMotion();
  // the graph's views first, then the pinned ones newest first, then the views built on the embedding
  const card = (c: LoopCard): Item => ({ key: `view:${c.id}`, name: c.name, meta: c.meta, hint: c.hint ?? c.name, on: !!c.on, suggested: c.suggested, thumb: c.thumb, apply: () => onPick?.(c.id) });
  const list: Item[] = [
    ...lead.map(card),
    ...[...views].reverse().map((v): Item => ({ key: v.id, name: v.name, meta: ago(v.created), hint: `${v.name}, pinned ${ago(v.created)}`, on: v.id === active, apply: () => onApply(v.id) })),
    ...tail.map(card),
  ];
  const n = list.length;
  const base = loopSolid(areaHeight);
  const looping = n > base;
  const { solid, slots } = useMemo(() => loopSlots(n, base), [n, base]);
  const places = useMemo(() => arcPlaces(solid), [solid]);
  const [turn, setTurn] = useState(0);
  useEffect(() => setTurn(0), [n]);
  const wheelAt = useRef(0);
  const spin = (d: number) => looping && setTurn((t) => (((t + d) % n) + n) % n);
  const onWheel = (e: WheelEvent) => {
    if (!looping || Math.abs(e.deltaY) < 4) return;
    const now = performance.now();
    if (now - wheelAt.current < 170) return; // one card per notch, however fast the wheel spins
    wheelAt.current = now;
    spin(e.deltaY > 0 ? 1 : -1);
  };

  if (!n)
    return open ? (
      <p
        role="status"
        className="pointer-events-auto absolute z-[16] w-[240px] rounded-xl border bg-card px-3 py-2 text-[12.5px] text-muted-foreground shadow-[var(--shadow)]"
        style={{ left: EDGE + 5, top: EDGE + BUTTON + 6 }}
      >
        {empty}
      </p>
    ) : null;

  // the place of the card j steps after the front one (the mockup's layoutPins)
  const slot = (j: number): Slot | null => {
    const at = (q: number, opacity: number, z: number, end?: Slot["end"]): Slot => ({ solid: !end, end, ...places[q]!, opacity, z });
    const tilt = (deg: number, opacity: number, z: number, end: Slot["end"]): Slot => ({ solid: false, end, x: 0, y: 0, deg, opacity, z });
    switch (slots[j]) {
      case "solid":
        return at(j, 1, 40 - j);
      // below: the next card half there, the one after almost gone
      case "b1":
        return at(solid, 0.55, 30, "b1");
      case "b2":
        return at(solid + 1, 0.24, 29, "b2");
      // above: the cards just turned past stay tilted about the pin, fading toward the top border
      case "t1":
        return tilt(-6, 0.72, 33, "t1");
      case "t2":
        return tilt(-12, 0.46, 32, "t2");
      case "t3":
        return tilt(-18, 0.22, 31, "t3");
      default:
        return null;
    }
  };
  const ease = "cubic-bezier(.32,.72,0,1)";
  return (
    <div
      role="list"
      aria-label={lead.length || tail.length ? "Views" : "Pinned views"}
      aria-hidden={!open}
      inert={!open}
      data-corners="pin-loop"
      onWheel={onWheel}
      className={cn("pointer-events-none absolute z-[16] transition-opacity duration-300 motion-reduce:transition-none", open ? "opacity-100" : "opacity-0")}
      style={{ left: LOOP_LEFT, top: LOOP_TOP, width: LOOP_W + 40, height: LOOP_H + (solid + 1) * STEP }}
    >
      {list.map((v, i) => {
        const j = (((i - turn) % n) + n) % n;
        const s = slot(j);
        // closed, the first few tuck behind the pin as a small pile; the rest wait there unseen
        const q = Math.min(j, 4);
        const transform = !open
          ? `translate(-12px,-12px) rotate(${q * 5}deg) scale(.6)`
          : s
            ? `translate(${s.x.toFixed(1)}px,${s.y.toFixed(1)}px) rotate(${s.deg.toFixed(2)}deg)`
            : `translate(${places[Math.min(solid, places.length - 1)]!.x.toFixed(1)}px,${(places[Math.min(solid, places.length - 1)]!.y + 20).toFixed(1)}px)`;
        const opacity = !open ? (j < 5 ? 1 : 0) : (s?.opacity ?? 0);
        const end = s?.end;
        // a faded card below turns the loop forward, one tilted above the pin turns it back
        const pressTurns = end ? (end.startsWith("b") ? 1 : -1) : 0;
        const live = open && !!s;
        return (
          <div
            key={v.key}
            role={live ? "listitem" : undefined}
            aria-hidden={!live || undefined}
            inert={!live}
            data-slot={s ? (end ?? "solid") : undefined}
            data-pos={j}
            className="absolute left-0 top-0"
            style={{
              zIndex: s?.z ?? 1,
              transform,
              transformOrigin: "0 0",
              opacity,
              transition: still ? undefined : `transform .45s ${ease}, opacity .45s`,
            }}
          >
            <button
              type="button"
              data-view={v.key}
              data-end={end}
              aria-current={v.on || undefined}
              aria-label={pressTurns ? `${v.name}, turn the pile${pressTurns < 0 ? " back" : ""}` : v.name}
              title={pressTurns ? `Turn the pile ${pressTurns < 0 ? "back " : ""}to ${v.name}` : v.hint}
              onClick={() => (pressTurns ? spin(pressTurns) : v.apply())}
              className={cn(
                "group relative block overflow-hidden rounded-[11px] border bg-card text-left shadow-[0_4px_12px_rgba(0,0,0,.13)] transition-[border-color,box-shadow] duration-150 motion-reduce:transition-none",
                live ? "pointer-events-auto" : "pointer-events-none",
                v.suggested && "border-dashed",
                "hover:border-primary hover:ring-1 hover:ring-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
              style={{ width: LOOP_W, height: LOOP_H }}
            >
              <GraphThumb kind={v.thumb} seed={v.key} className={cn("absolute inset-0 size-full", v.suggested && "opacity-75")} />
              <span className="absolute inset-x-0 bottom-0 flex items-baseline gap-2 border-t bg-card px-2.5 py-1.5 text-[12.5px]">
                {v.on && <span aria-hidden className="size-1.5 flex-none self-center rounded-full bg-primary" />}
                <span className={cn("min-w-0 truncate font-semibold", v.on && "text-primary")}>{v.name}</span>
                {v.meta && (
                  <small className={cn("ml-auto flex-none text-[11px] text-muted-foreground transition-opacity", !v.suggested && "opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100")}>{v.meta}</small>
                )}
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
