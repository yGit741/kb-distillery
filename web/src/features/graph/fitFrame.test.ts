import { describe, expect, it } from "vitest";
import { fitFrame } from "./fitFrame";
import { SEARCH_LINE_H, SHELL_TOP, SHELL_TOP_FOLDED } from "./shell/layout";

/** Where a graph point lands on screen under the camera `fitFrame` returns (the view's centre is the canvas's centre). */
const screenY = (y: number, cam: { y: number; k: number }, height: number) => height / 2 + (y - cam.y) * cam.k;
const screenX = (x: number, cam: { x: number; k: number }, width: number) => width / 2 + (x - cam.x) * cam.k;

describe("fitFrame", () => {
  const W = 691;
  const H = 450; // the right pane of the full chat at 1440x900

  for (const top of [SHELL_TOP, SHELL_TOP_FOLDED]) {
    it(`keeps a tall cluster below the search line (shell top ${top})`, () => {
      const clearance = top + SEARCH_LINE_H + 56;
      const tall = { x0: -60, x1: 60, y0: -900, y1: 900 };
      const cam = fitFrame(tall, W, H, { left: 0, top: clearance, pad: 72 });
      expect(screenY(tall.y0, cam, H)).toBeGreaterThanOrEqual(clearance - 0.5);
      expect(screenY(tall.y1, cam, H)).toBeLessThanOrEqual(H - 72 + 0.5);
    });
  }

  it("without the search line obstacle the same cluster sits under the line", () => {
    const tall = { x0: -60, x1: 60, y0: -900, y1: 900 };
    const cam = fitFrame(tall, W, H, { left: 0, top: 0, pad: 20 });
    expect(screenY(tall.y0, cam, H)).toBeLessThan(SHELL_TOP + SEARCH_LINE_H);
  });

  it("keeps the pages right of a panel and inside the pad", () => {
    const wide = { x0: -900, x1: 900, y0: -10, y1: 10 };
    const cam = fitFrame(wide, 1040, 900, { left: 400, top: 100, pad: 72 });
    expect(screenX(wide.x0, cam, 1040)).toBeGreaterThanOrEqual(400 + 72 - 0.5);
    expect(screenX(wide.x1, cam, 1040)).toBeLessThanOrEqual(1040 - 72 + 0.5);
  });

  it("a top clearance below the pad changes nothing, and a lone page is not blown up", () => {
    const lone = { x0: 5, x1: 5, y0: 5, y1: 5 };
    const a = fitFrame(lone, W, H, { left: 0, top: 10, pad: 72 });
    const b = fitFrame(lone, W, H, { left: 0, top: 72, pad: 72 });
    expect(a).toEqual(b);
    expect(a.k).toBe(2.2);
  });
});
