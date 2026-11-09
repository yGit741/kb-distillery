import { describe, expect, it } from "vitest";
import { BUTTON, EDGE, FAN_GAP, FAN_STACK_EDGE, fanCapacity, fanPoint, fanReach, fanTransform, legendHeight, legendTop, lensHover, lensLayout, lensTops, SLOT, THUMB, type LensItem } from "./geometry";

const rows = (n: number): LensItem[] => Array.from({ length: n }, () => ({ kind: "row" as const, hb: SLOT.row }));
/** a list like the real one: pins, the "+" card, a divider, the Recent stack and some steps */
const listOf = (pins: number, steps = 0): LensItem[] => [
  ...rows(pins),
  { kind: "add", hb: SLOT.add },
  { kind: "div", hb: SLOT.div },
  { kind: "stack", hb: SLOT.stack },
  ...rows(steps),
];

describe("fan geometry", () => {
  it("puts every card on one circle: its distance from the circle's centre is the radius", () => {
    for (let i = 0; i < 8; i++) {
      const p = fanPoint(i);
      // the circle's centre is level with the button, R away from the edge the fan grows from
      expect(Math.hypot(900 - p.x, p.y)).toBeCloseTo(900, 6);
    }
  });

  it("starts almost straight and opens wider with each card", () => {
    expect(fanPoint(0).deg).toBeCloseTo((0.03 * 180) / Math.PI, 6);
    const steps = [0, 1, 2, 3, 4].map((i) => fanPoint(i + 1).y - fanPoint(i).y);
    for (let i = 1; i < steps.length; i++) expect(steps[i]!).toBeGreaterThan(steps[i - 1]! - 0.001);
  });

  it("Think is Agent turned 180 degrees: the same offsets, mirrored through the centre, the same tilt", () => {
    for (let i = 0; i < 6; i++) {
      const a = fanTransform("agent", i).match(/-?\d+(\.\d+)?/g)!.map(Number);
      const t = fanTransform("think", i).match(/-?\d+(\.\d+)?/g)!.map(Number);
      expect(t[0]).toBeCloseTo(-a[0]!, 1);
      expect(t[1]).toBeCloseTo(-a[1]!, 1);
      expect(t[2]).toBeCloseTo(a[2]!, 1);
    }
  });

  it("Pins is Agent mirrored top to bottom: it grows down from the top-left with the same tilt as Think", () => {
    for (let i = 0; i < 6; i++) {
      const a = fanTransform("agent", i).match(/-?\d+(\.\d+)?/g)!.map(Number);
      const p = fanTransform("pins", i).match(/-?\d+(\.\d+)?/g)!.map(Number);
      expect(p[0]).toBeCloseTo(a[0]!, 1);
      expect(p[1]).toBeCloseTo(-a[1]!, 1);
      expect(p[2]).toBeCloseTo(a[2]!, 1);
    }
  });

  it("leaves 10px between the corner button and the first card", () => {
    // the first card's picture ends FAN_STACK_EDGE + fanPoint(0).y from the screen edge; the button ends EDGE + BUTTON
    expect(FAN_STACK_EDGE + fanPoint(0).y - (EDGE + BUTTON)).toBeCloseTo(FAN_GAP, 6);
  });

  it("fits fewer cards on a short screen, at least two, and two fans never reach each other", () => {
    expect(fanCapacity(1000)).toBeGreaterThanOrEqual(fanCapacity(700));
    expect(fanCapacity(200)).toBe(2);
    for (const h of [500, 600, 700, 900, 1200]) {
      const n = fanCapacity(h);
      if (n > 2) expect(2 * fanReach(n)).toBeLessThanOrEqual(h);
    }
    // sanity: the picture is as tall as the mockup's
    expect(THUMB.h).toBe(50);
  });
});

describe("pinned list lens", () => {
  it("at rest nothing grows or moves", () => {
    const t = lensLayout(listOf(4), -1);
    expect(t.every((x) => x.s === 1 && x.dy === 0)).toBe(true);
  });

  it("grows the hovered row to 1.55 and the neighbours less, dividers never", () => {
    const items = listOf(6);
    const t = lensLayout(items, 3);
    expect(t[3]!.s).toBeCloseTo(1.55, 6);
    expect(t[2]!.s).toBeLessThan(t[3]!.s);
    expect(t[2]!.s).toBeGreaterThan(t[1]!.s);
    expect(t[1]!.s).toBeGreaterThan(1);
    expect(t[0]!.s).toBe(1);
    const div = items.findIndex((i) => i.kind === "div");
    expect(t[div]!.s).toBe(1);
  });

  it("never overlaps, keeps the hovered row in place, with at least 8px between pictures, for every hover index, with 40 rows", () => {
    const items = listOf(40, 6);
    const tops = lensTops(items);
    for (let h = 0; h < items.length; h++) {
      if (items[h]!.kind === "div") continue;
      const t = lensLayout(items, h, 100); // scrolled: no top clamp
      const box = items.map((it, i) => {
        const c = tops[i]! + it.hb / 2 + t[i]!.dy;
        const half = (it.hb * t[i]!.s) / 2;
        // the picture inside the slot is 20px tall (a stack 20, an "+" card 20)
        const pic = (it.kind === "div" ? 1 : 20 * t[i]!.s) / 2;
        return { top: c - half, bottom: c + half, picTop: c - pic, picBottom: c + pic };
      });
      for (let i = 1; i < box.length; i++) {
        expect(box[i]!.top).toBeGreaterThanOrEqual(box[i - 1]!.bottom - 1e-6);
        expect(box[i]!.picTop - box[i - 1]!.picBottom).toBeGreaterThanOrEqual(8);
      }
      expect(t[h]!.dy).toBeCloseTo(0, 6);
    }
  });

  it("at the top of the list the first row does not grow out of it", () => {
    const items = listOf(5);
    const t = lensLayout(items, 0, 0);
    expect(t[0]!.dy - (items[0]!.hb * (t[0]!.s - 1)) / 2).toBeGreaterThanOrEqual(-1e-6);
  });

  it("keeps the current row until the pointer is 6px past it", () => {
    const items = rows(3);
    const tops = lensTops(items);
    expect(lensHover(items, tops, 50, -1)).toBe(1);
    expect(lensHover(items, tops, 40, 1)).toBe(1);
    expect(lensHover(items, tops, 44 - 4, 0)).toBe(0);
    expect(lensHover(items, tops, 44 + 3, 0)).toBe(0);
    expect(lensHover(items, tops, 44 + 8, 0)).toBe(1);
  });
});

describe("colour legend position", () => {
  it("is centred on the right edge, and the same while Think is closed", () => {
    const h = legendHeight(10, false);
    expect(legendTop({ areaHeight: 800, height: h, thinkOpen: false, thinkCards: 5 })).toBeCloseTo((800 - h) / 2, 6);
  });

  it("slides below the Think fan's arc when Think opens, for any number of cards", () => {
    for (const cards of [1, 2, 3, 4, 5, 7]) {
      for (const open of [false, true]) {
        const h = legendHeight(10, open);
        const top = legendTop({ areaHeight: 900, height: h, thinkOpen: true, thinkCards: cards });
        expect(top).toBeGreaterThanOrEqual(fanReach(cards) + 11);
        expect(top + h).toBeLessThanOrEqual(900);
      }
    }
  });
});
