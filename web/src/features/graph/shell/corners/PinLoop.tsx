import { ChevronRight } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState, type WheelEvent } from "react";
import { cn } from "@/lib/utils";
import { ago, type PinnedView } from "./api";
import { BUTTON, EDGE } from "./geometry";
import { useReducedMotion } from "./motion";
import { GraphThumb, type ThumbKind } from "./Thumb";
import type { ViewAbout } from "./viewAbout";

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
 * card is solid. Past it both ends show, as in the mockup: two cards fading below (b1 half there, b2 almost gone) and
 * two turned past, tilted above the pin (t1, t2; a third, t3, once there are more cards). The solid run gives way
 * (never below two) so the four ends fit.
 */
export function loopSlots(n: number, base: number): { solid: number; slots: (SlotName | null)[] } {
  if (n <= base) return { solid: n, slots: Array.from({ length: n }, (): SlotName => "solid") };
  // room for four ends (two fading below, two turned past above) before the solid run takes the window's count
  const solid = Math.max(2, Math.min(base, n - 4));
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

/** flag graph.artifacts: a card unfolded from a pile is clearly smaller than a card of the loop (same shape). */
export const SUB_W = 148;
export const SUB_H = 84;
/** each unfolded card lies over the right edge of the one before by this much (its name, on the left, stays clear) */
export const ROW_OVERLAP = 26;
/** a small card's picture is as tall as the card and keeps its shape (100 x 64), centred in the part no card covers */
const SUB_ART_W = (SUB_H * 100) / 64;
/** the "?" explanation under an unfolded card */
const ABOUT_W = 304;
/**
 * the row starts this far right of its card (the unfold button sits in the gap) and this far below the card's top: a
 * pile only unfolds from the loop's top place, beside the search line, and this drop keeps the row clear under that line
 */
const ROW_GAP = 22;
const ROW_DROP = 40;
/**
 * px from one unfolded card to the next: each card partly over the one before. In a narrow graph area the cards close
 * up a little more, down to TIGHT (every name still reads); past that the cards break into a second and a third row,
 * and only then close up further.
 */
const ROW_STEP = SUB_W - ROW_OVERLAP;
const ROW_STEP_TIGHT = 108;
const ROW_STEP_MIN = 48;
const ROW_MAX = 3;
/** from the top of one row to the top of the next */
const ROW_PITCH = SUB_H + 14;
/** each row hangs like a garland: its first card tilts down by this much, its last one up by as much */
const ROW_SAG = 2.4;
/** kept free at the right end of a row (`areaWidth` already leaves out the colour legend standing on that edge) */
const ROW_MARGIN = 20;
/** how many tucked cards show an edge under their card */
const PEEKS = 3;

/** Flag graph.artifacts: how many rows `n` unfolded cards take in `room` px (measured from their card's left edge). */
export function rowCount(n: number, room = Infinity): number {
  const fit = Math.max(1, Math.floor((room - LOOP_W - ROW_GAP - SUB_W) / ROW_STEP_TIGHT) + 1);
  return Math.max(1, Math.min(ROW_MAX, Math.ceil(n / fit)));
}

/**
 * Flag graph.artifacts: where the cards of an unfolded pile sit, in the frame of their card (the loop's top one, which is
 * level). They run to the right in a row with a slight sag (first card down, last card up), so the row hangs rather
 * than lies; cards that do not fit `room` go on to the next row, the rows as even as they can be. `rows` fixes the
 * number of rows (the loop keeps the count it unfolded with, so a legend that grows only closes the cards up a little).
 */
export function rowPlaces(n: number, room = Infinity, rows = rowCount(n, room)): { x: number; y: number; deg: number }[] {
  if (n < 1) return [];
  const per = Math.ceil(n / rows);
  const step = per > 1 ? Math.max(ROW_STEP_MIN, Math.min(ROW_STEP, (room - LOOP_W - ROW_GAP - SUB_W) / (per - 1))) : ROW_STEP;
  const out: { x: number; y: number; deg: number }[] = [];
  for (let r = 0; r * per < n; r++) {
    const m = Math.min(per, n - r * per);
    const turn = (k: number) => ROW_SAG * (1 - (2 * k + 1) / m);
    let x = LOOP_W + ROW_GAP;
    let y = ROW_DROP + r * ROW_PITCH;
    for (let k = 0; k < m; k++) {
      out.push({ x, y, deg: turn(k) });
      const mid = (((turn(k) + turn(k + 1)) / 2) * Math.PI) / 180;
      x += step * Math.cos(mid);
      y += step * Math.sin(mid);
    }
  }
  return out;
}

/**
 * Flag graph.artifacts: how far below the graph area's top edge `rows` rows of unfolded cards reach (the sag included). The
 * graph is framed below this while they are out.
 */
export function rowReach(rows: number): number {
  return rows < 1 ? 0 : LOOP_TOP + ROW_DROP + (rows - 1) * ROW_PITCH + SUB_H + 20;
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
  /** flag graph.artifacts: the other views of this card's layer, tucked under it as a pile and unfolded into a row */
  subs?: readonly LoopCard[];
  /** flag graph.artifacts: what the view is drawn from; an unfolded card with it carries a "?" that shows it */
  about?: ViewAbout;
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
  /** flag graph.artifacts: the card whose pile is unfolded, and how the round button on a card asks to unfold or fold it */
  pile?: string | null;
  onPile?: (key: string | null) => void;
  /** the width an unfolded row may reach (the graph area's, less the colour legend): the row never runs past it */
  areaWidth?: number;
  /** told how far down the unfolded cards reach, in px from the graph area's top (0: none out) */
  onReach?: (px: number) => void;
  /** flag graph.artifacts: the wheel turns the loop even when every card fits (the next card comes up to the top place) */
  wheelTurns?: boolean;
  /** flag graph.artifacts: the unfolded card whose "?" explanation is open, and how a "?" asks to open or close it */
  about?: string | null;
  onAbout?: (key: string | null) => void;
}

type Item = { key: string; name: string; meta?: string; hint: string; on: boolean; suggested?: boolean; thumb?: ThumbKind; apply: () => void; subs?: Item[]; about?: ViewAbout };

const FACE =
  "group relative block overflow-hidden rounded-[11px] border bg-card text-left shadow-[0_4px_12px_rgba(0,0,0,.13)] transition-[border-color,box-shadow] duration-150 motion-reduce:transition-none hover:border-primary hover:ring-1 hover:ring-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * The face of a card: its picture over a line with its name. A card whose pile holds the view on screen names that
 * view on a small blue tag just above the line (the part of a card the one above it never covers). `small` is a card
 * unfolded from a pile; `clear` is how much of its width, from the left, the next card of the row leaves uncovered.
 */
function CardFace({ v, live, end, label, title, onClick, className, small, clear = SUB_W }: { v: Item; live: boolean; end?: Slot["end"]; label: string; title: string; onClick: () => void; className?: string; small?: boolean; clear?: number }) {
  const under = v.on ? undefined : v.subs?.find((c) => c.on);
  const meta = v.meta;
  return (
    <button
      type="button"
      data-view={v.key}
      data-end={end}
      aria-current={v.on || undefined}
      aria-label={label}
      title={title}
      onClick={onClick}
      className={cn(FACE, live ? "pointer-events-auto" : "pointer-events-none", v.suggested && "border-dashed", className)}
      style={small ? { width: SUB_W, height: SUB_H } : { width: LOOP_W, height: LOOP_H }}
    >
      {small ? (
        <span aria-hidden className="absolute inset-y-0 transition-[left] duration-500 motion-reduce:transition-none" style={{ left: (Math.max(clear, SUB_W * 0.6) - SUB_ART_W) / 2, width: SUB_ART_W }}>
          <GraphThumb kind={v.thumb} seed={v.key} className="size-full" />
        </span>
      ) : (
        <GraphThumb kind={v.thumb} seed={v.key} className={cn("absolute inset-0 size-full", v.suggested && "opacity-75")} />
      )}
      {under && (
        <span data-under className="absolute bottom-[35px] right-3 max-w-[70%] truncate rounded-full border border-primary/40 bg-card px-2 py-px text-[10.5px] font-medium text-primary shadow-[0_1px_3px_rgba(0,0,0,.12)]">
          {under.name}
        </span>
      )}
      <span className={cn("absolute inset-x-0 bottom-0 flex items-baseline border-t bg-card", small ? "gap-1.5 px-2 py-1 text-[11.5px]" : "gap-2 px-2.5 py-1.5 text-[12.5px]")}>
        {(v.on || under) && <span aria-hidden className="size-1.5 flex-none self-center rounded-full bg-primary" />}
        <span className={cn("min-w-0 truncate font-semibold", meta && "max-w-[72%] flex-none", v.on && "text-primary")}>{v.name}</span>
        {/* the small grey text is always there, as in the mockup; it gives way before the name does */}
        {meta && <small className="ml-auto min-w-0 shrink-[4] truncate text-[11px] text-muted-foreground">{meta}</small>}
      </span>
    </button>
  );
}

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
export function PinLoop({ open, views, lead = [], tail = [], onPick, active, areaHeight, onApply, empty, pile = null, onPile, areaWidth = 1280, onReach, wheelTurns = false, about = null, onAbout }: Props) {
  const still = useReducedMotion();
  // the graph's views first, then the pinned ones newest first, then the views built on the embedding
  const card = (c: LoopCard): Item => ({ key: `view:${c.id}`, name: c.name, meta: c.meta, hint: c.hint ?? c.name, on: !!c.on, suggested: c.suggested, thumb: c.thumb, apply: () => onPick?.(c.id), subs: c.subs?.map(card), about: c.about });
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
  // flag graph.artifacts: a pile unfolds only from the top place, so its card rises there first (the loop turns to it) and
  // goes back to its own place when the row folds. The top place is level and beside the search line, clear of the graph.
  const lifted = pile ? list.findIndex((v) => v.key === pile && !!v.subs?.length) : -1;
  const at = lifted >= 0 ? lifted : turn;
  const room = areaWidth - LOOP_LEFT - ROW_MARGIN;
  // the number of rows is decided when the pile unfolds and kept while it is out: picking a view whose legend is wider
  // closes the cards up a little, it never sends them to another row under the pointer
  const rowsOf = useRef<{ key: string; rows: number } | null>(null);
  if (lifted < 0 || !open) rowsOf.current = null;
  else if (rowsOf.current?.key !== pile) rowsOf.current = { key: pile!, rows: rowCount(list[lifted]!.subs!.length, room) };
  const rows = rowsOf.current?.rows ?? 0;
  const reach = rowReach(rows);
  useEffect(() => onReach?.(reach), [reach, onReach]);
  const wheelAt = useRef(0);
  // a loop longer than its window always turns; a short one turns with the wheel under flag graph.artifacts, its cards
  // going round the same places (the top card goes to the bottom one)
  const turns = looping || (wheelTurns && n > 1);
  const spin = (d: number) => {
    if (!turns) return;
    // turning the loop folds an unfolded row; the loop carries on from where the lifted card left it
    setTurn((((at + d) % n) + n) % n);
    if (lifted >= 0) onPile?.(null);
  };
  const onWheel = (e: WheelEvent) => {
    if (!turns || Math.abs(e.deltaY) < 4) return;
    const now = performance.now();
    // one card per notch, however fast the wheel spins; a short loop turns slower, so a trackpad swipe moves one card
    if (now - wheelAt.current < (looping ? 170 : 260)) return;
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
  // the "?" explanation: under its card (the lifted card is level at the loop's origin, so a row place is a place of the loop)
  const told = lifted >= 0 && open ? (list[lifted]!.subs ?? []).findIndex((c) => c.key === about && !!c.about) : -1;
  const toldCard = told >= 0 ? list[lifted]!.subs![told]! : null;
  const toldAt = told >= 0 ? rowPlaces(list[lifted]!.subs!.length, room, rows)[told]! : null;
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
        const j = (((i - at) % n) + n) % n;
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
        // flag graph.artifacts: the views tucked under this card, and the row they unfold into
        const subs = v.subs ?? [];
        const front = live && !!s?.solid; // a solid card of the open loop
        const unfolded = front && pile === v.key;
        const row = unfolded ? rowPlaces(subs.length, room, rows) : [];
        const move = `transform .45s ${ease}, opacity .45s`;
        return (
          <Fragment key={v.key}>
            <div
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
                transition: still ? undefined : move,
              }}
            >
              <CardFace
                v={v}
                live={live}
                end={end}
                label={pressTurns ? `${v.name}, turn the pile${pressTurns < 0 ? " back" : ""}` : v.name}
                title={pressTurns ? `Turn the pile ${pressTurns < 0 ? "back " : ""}to ${v.name}` : v.hint}
                onClick={() => (pressTurns ? spin(pressTurns) : v.apply())}
                className={subs.length ? "z-[10]" : undefined}
              />
              {subs.length > 0 && (
                <div role="group" aria-label={`More ${v.name} views`} data-pile={v.key} data-unfolded={unfolded || undefined} inert={!unfolded}>
                  {subs.map((c, k) => {
                    // folded, the first few lie under the card a little lower, further right and more turned, so their edges show
                    const tuck = Math.min(k, PEEKS - 1) + 1;
                    const p = row[k];
                    // how much of this card the next one in its row leaves uncovered (the last of a row: all of it)
                    const next = row[k + 1];
                    const clear = p && next && next.y - p.y < SUB_H / 2 && next.x > p.x ? next.x - p.x : SUB_W;
                    // out one after the other from the nearest (once the card is on its way up); back in from the farthest
                    const wait = still ? 0 : unfolded ? (lifted !== turn ? 160 : 0) + k * 45 : (subs.length - 1 - k) * 30;
                    return (
                      <div
                        key={c.key}
                        className="absolute left-0 top-0"
                        style={{
                          zIndex: unfolded ? k + 1 : PEEKS - Math.min(k, PEEKS),
                          // tucked, a small card is stretched to its card's size, so its edges show past it
                          transform: p
                            ? `translate(${p.x.toFixed(1)}px,${p.y.toFixed(1)}px) rotate(${p.deg.toFixed(2)}deg)`
                            : `translate(${tuck * 6}px,${tuck * 4}px) rotate(${(tuck * 0.8).toFixed(1)}deg) scale(${(LOOP_W / SUB_W).toFixed(3)},${(LOOP_H / SUB_H).toFixed(3)})`,
                          transformOrigin: "0 0",
                          opacity: unfolded ? 1 : front && k < PEEKS ? 1 : 0,
                          transition: still ? undefined : `transform .5s ${ease} ${wait}ms, opacity .3s ${wait}ms`,
                        }}
                      >
                        <CardFace v={c} live={unfolded} label={c.name} title={c.hint} onClick={c.apply} small clear={clear} />
                        {c.about && (
                          <button
                            type="button"
                            data-about={c.key}
                            aria-expanded={about === c.key}
                            aria-controls={about === c.key ? "pin-loop-about" : undefined}
                            aria-label={`What is ${c.name} based on?`}
                            title={`What ${c.name} is based on`}
                            onClick={() => onAbout?.(about === c.key ? null : c.key)}
                            className={cn(
                              "absolute left-[5px] top-[5px] grid size-[18px] place-items-center rounded-full border text-[11px] font-semibold leading-none shadow-[0_1px_3px_rgba(0,0,0,.16)] transition-[background-color,border-color,color,opacity] duration-200 motion-reduce:transition-none",
                              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                              unfolded ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
                              about === c.key ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:border-primary hover:text-primary",
                            )}
                          >
                            ?
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            {/* the unfold button rides its card's right edge, over every card of the loop so a pile above never hides it */}
            {subs.length > 0 && (
              <button
                type="button"
                data-unfold={v.key}
                aria-expanded={unfolded}
                aria-label={`${unfolded ? "Fold" : "Unfold"} the ${v.name} views`}
                data-lifts={!unfolded && j > 0 ? true : undefined}
                title={unfolded ? `Fold the ${v.name} views` : `${subs.length} more ${v.name} view${subs.length === 1 ? "" : "s"}: ${subs.map((c) => c.name).join(", ")}`}
                inert={!front}
                onClick={() => onPile?.(unfolded ? null : v.key)}
                className={cn(
                  "absolute left-0 top-0 grid size-6 place-items-center rounded-full border shadow-[0_1px_4px_rgba(0,0,0,.18)] transition-[background-color,border-color,color] duration-200 motion-reduce:transition-none",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  front ? "pointer-events-auto" : "pointer-events-none",
                  unfolded ? "border-primary bg-primary text-primary-foreground" : "bg-card text-foreground hover:border-primary hover:text-primary",
                )}
                style={{
                  zIndex: 50,
                  transform: `${transform} translate(${LOOP_W - 6}px,${LOOP_H / 2 - 12}px)`,
                  transformOrigin: "0 0",
                  opacity: front ? 1 : 0,
                  transition: still ? undefined : `${move}, background-color .2s, border-color .2s, color .2s`,
                }}
              >
                <ChevronRight aria-hidden strokeWidth={2.2} className={cn("size-3.5 transition-transform duration-300 motion-reduce:transition-none", unfolded && "rotate-180")} />
              </button>
            )}
          </Fragment>
        );
      })}
      {toldCard?.about && toldAt && (
        <div
          id="pin-loop-about"
          role="region"
          aria-label={`What ${toldCard.name} is based on`}
          data-about-panel={toldCard.key}
          onWheel={(e) => e.stopPropagation()}
          className="pointer-events-auto absolute overflow-y-auto rounded-xl border bg-card px-3.5 py-3 text-[12px] leading-snug shadow-[0_8px_28px_rgba(0,0,0,.18)]"
          style={{
            zIndex: 60,
            width: ABOUT_W,
            left: Math.max(0, Math.min(toldAt.x, room - ABOUT_W)),
            top: toldAt.y + SUB_H + 10,
            maxHeight: Math.max(120, areaHeight - LOOP_TOP - toldAt.y - SUB_H - 26),
          }}
        >
          <p className="text-[13px] font-semibold">{toldCard.name}</p>
          <p className="mt-0.5 text-muted-foreground">{toldCard.about.what}</p>
          <p className="mt-2.5 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">Based on</p>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
            {toldCard.about.based.map((b) => (
              <Fragment key={b.label}>
                <dt className="text-muted-foreground">{b.label}</dt>
                <dd className="min-w-0 break-words">{b.text}</dd>
              </Fragment>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
