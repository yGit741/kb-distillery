/**
 * The pure geometry of the corner controls: where the fan cards sit on their arc, how the pinned-views list
 * grows under the pointer (the Dock lens) and where the colour legend sits. No DOM here, so every number is
 * testable (jsdom has no layout). The values come from the approved mockup.
 */

/** Distance of a corner button's box from the screen edge, the same on all four corners. */
export const EDGE = 14;
/** Corner button box (the icon is 22px inside it). */
export const BUTTON = 44;

// ---- fans ----------------------------------------------------------------------------------------------

/** One true arc: every card sits on a circle of this radius, whose centre is level with the button. */
export const FAN_R = 900;
export const FAN_STEP = 58 / FAN_R;
export const THUMB = { w: 72, h: 50 } as const;
export const PILL_W = 280;
/** Space between a corner button and its first card. */
export const FAN_GAP = 10;

export interface FanPoint {
  /** how far the card moved away from the screen edge (towards the middle of the screen), px */
  x: number;
  /** how far it moved away from its corner along the edge, px */
  y: number;
  /** its tilt, degrees (the fan opens like a hand of cards) */
  deg: number;
}

/** Card `i` on the arc; card 0 is almost straight, the spacing widens a little with every card. */
export function fanPoint(i: number): FanPoint {
  const a = FAN_STEP * i * (1 + 0.05 * i) + 0.03;
  return { x: FAN_R * (1 - Math.cos(a)), y: FAN_R * Math.sin(a), deg: (a * 180) / Math.PI };
}

export type FanKind = "agent" | "think";

/**
 * The CSS transform of card `i`. Agent grows up from the bottom-left, Think is the same arc turned 180
 * degrees about the middle of the screen: it grows down from the top-right (the tilt keeps its sign, the
 * card's text is never upside down).
 */
export function fanTransform(kind: FanKind, i: number): string {
  const p = fanPoint(i);
  const [dx, dy] = kind === "agent" ? [p.x, -p.y] : [-p.x, p.y];
  return `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px) rotate(${p.deg.toFixed(2)}deg)`;
}

/** The resting (folded) transform every card starts from and returns to. */
export const FAN_FOLDED = "translate(0px, 30px) scale(0.5)";

/**
 * Where the fan's stack starts, measured from the screen edge it grows away from (bottom edge for Agent, top edge
 * for Think): the folded cards sit here, and card 0 ends up exactly `FAN_GAP` clear of the corner button.
 */
export const FAN_STACK_EDGE = EDGE + BUTTON + FAN_GAP - fanPoint(0).y;
/** The stack also sits a little inside the button's side edge, so the arc starts under the button's centre. */
export const FAN_STACK_SIDE = EDGE + 4;

/**
 * How many cards fit on one fan: each fan may use half of the free height, so both can be open together
 * without touching. Always at least two.
 */
export function fanCapacity(areaHeight: number, max = 7): number {
  const half = (areaHeight - 2 * (EDGE + BUTTON + FAN_GAP)) / 2;
  let n = 0;
  while (n < max && fanPoint(n).y + THUMB.h / 2 + 8 <= half) n += 1;
  return Math.max(2, n);
}

/** Distance from the screen's top (Think) or bottom (Agent) edge to the far side of the last of `n` cards. */
export function fanReach(n: number): number {
  if (n <= 0) return EDGE + BUTTON;
  const p = fanPoint(n - 1);
  const rad = (p.deg * Math.PI) / 180;
  return FAN_STACK_EDGE + THUMB.h / 2 + p.y + (THUMB.h / 2) * Math.cos(rad) + (THUMB.w / 2) * Math.sin(rad);
}

// ---- colour legend ---------------------------------------------------------------------------------------

export const LEGEND_REST_ROW = 10;
export const LEGEND_OPEN_ROW = 24;
export const LEGEND_PAD = 8;

/** Height of the legend: a tight stack at rest, spread into names when pressed. */
export const legendHeight = (rows: number, open: boolean): number => 2 * LEGEND_PAD + rows * (open ? LEGEND_OPEN_ROW : LEGEND_REST_ROW) + (open ? 22 : 2);

/**
 * Top of the legend inside the screen area: centred on the right edge, and while the Think fan is open pushed
 * down below the fan's arc so the two never overlap. The bottom keeps clear of the types handle.
 */
export function legendTop(o: { areaHeight: number; height: number; thinkOpen: boolean; thinkCards: number }): number {
  const centred = (o.areaHeight - o.height) / 2;
  if (!o.thinkOpen) return Math.max(EDGE, centred);
  const below = fanReach(o.thinkCards) + 12;
  const lowest = o.areaHeight - o.height - (EDGE + 30);
  return Math.max(Math.min(Math.max(centred, below), lowest), Math.min(below, o.areaHeight - o.height));
}

// ---- pinned views list: the Dock lens --------------------------------------------------------------------

export type LensKind = "row" | "add" | "div" | "stack";
export interface LensItem {
  kind: LensKind;
  /** height of its slot at rest */
  hb: number;
}

export const SLOT: Record<LensKind, number> = { row: 44, div: 18, stack: 48, add: 40 };
export const LENS_MAX = 1.55;
/** How much the neighbours of the hovered row grow: the hovered row 1, then 42%, then 12% of the growth. */
const FALLOFF = [1, 0.42, 0.12];
/** The ")" curve: how far a row sits from the list's edge at the middle of the visible height. */
export const BOW = 56;

export function lensTops(items: readonly LensItem[]): number[] {
  const tops: number[] = [];
  let y = 0;
  for (const it of items) {
    tops.push(y);
    y += it.hb;
  }
  return tops;
}

export interface LensTarget {
  /** scale about the row's left-centre */
  s: number;
  /** vertical shift, px: the grown rows push their neighbours apart like the Dock, so they never overlap */
  dy: number;
  /** 0..1: how much of the growth this row has */
  g: number;
}

/**
 * Where every row should be while the pointer is over row `hovered` (-1 = at rest). The hovered row grows to
 * `LENS_MAX`, its neighbours less; every row's extra height is added to the rows after it, and the whole column
 * is re-centred on the hovered row, so slots never overlap. Dividers never grow.
 */
export function lensLayout(items: readonly LensItem[], hovered: number, scrollTop = 0, max = LENS_MAX): LensTarget[] {
  const tg: LensTarget[] = items.map((it, i) => {
    let g = 0;
    if (hovered >= 0 && it.kind !== "div") {
      let dist = 0;
      const a = Math.min(i, hovered);
      const b = Math.max(i, hovered);
      for (let j = a + 1; j <= b; j++) if (items[j]!.kind !== "div") dist += 1;
      g = FALLOFF[dist] ?? 0;
    }
    return { g, s: it.kind === "div" ? 1 : 1 + (max - 1) * g, dy: 0 };
  });
  let anchor = 0;
  if (hovered >= 0) {
    items.forEach((it, i) => {
      const ex = it.hb * (tg[i]!.s - 1);
      if (i < hovered) anchor += ex;
      else if (i === hovered) anchor += ex / 2;
    });
  }
  let acc = 0;
  items.forEach((it, i) => {
    const ex = it.hb * (tg[i]!.s - 1);
    tg[i]!.dy = acc + ex / 2 - anchor;
    acc += ex;
  });
  // at the top of the list the first row may not grow upwards out of the list
  if (items.length && scrollTop < 4) {
    const top0 = tg[0]!.dy - (items[0]!.hb * (tg[0]!.s - 1)) / 2;
    if (top0 < 0) for (const t of tg) t.dy -= top0;
  }
  return tg;
}

/** Which row the pointer is on, with hysteresis: it stays on the current row until 6px past its edge. */
export function lensHover(items: readonly LensItem[], tops: readonly number[], p: number, prev: number): number {
  const cand = items.findIndex((it, i) => p >= tops[i]! && p < tops[i]! + it.hb);
  if (cand < 0 || items[cand]!.kind === "div") return prev;
  if (prev < 0 || prev >= items.length) return cand;
  const h0 = items[prev]!;
  return p < tops[prev]! - 6 || p > tops[prev]! + h0.hb + 6 ? cand : prev;
}

/** Horizontal offset of a row whose centre is `d` (-1..1 of the visible half height) from the middle: the ")" bow. */
export const bowOffset = (d: number): number => BOW * (1 - Math.max(-1.3, Math.min(1.3, d)) ** 2);
