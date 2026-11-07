import { describe, expect, it } from "vitest";
import type { CanvasColors } from "../canvasTheme";
import { drawReplayMark, LIT_DIM, type ReplayDrawing } from "./replayDraw";
import type { ReplayView } from "./replay";

const COLORS: Record<"light" | "dark", CanvasColors> = {
  light: { text: "#18181b", background: "#ffffff", link: "#71717a", ring: "#2563eb", muted: "#71717a", warn: "#ca8a04", font: "sans-serif" },
  dark: { text: "#fafafa", background: "#09090b", link: "#a1a1aa", ring: "#60a5fa", muted: "#a1a1aa", warn: "#facc15", font: "sans-serif" },
};

/** a canvas that records, per stroke, the dash pattern, width and colour in force */
function recorder() {
  let dash: number[] = [];
  let width = 0;
  let style = "";
  const strokes: { dash: number[]; width: number; style: string }[] = [];
  const ctx = {
    save() {},
    restore() {},
    beginPath() {},
    arc() {},
    fill() {},
    stroke: () => strokes.push({ dash: [...dash], width, style }),
    setLineDash: (d: number[]) => void (dash = d),
    set lineWidth(v: number) { width = v; },
    set strokeStyle(v: string) { style = v; },
    set fillStyle(_v: string) {},
  };
  return { ctx: ctx as unknown as CanvasRenderingContext2D, strokes };
}

const view = (roles: [string, "seen" | "read" | "cited"][], current: string[] = []): ReplayView => ({ roles: new Map(roles), current: new Set(current), path: [], atEnd: true });
const drawing = (v: ReplayView, candidates: string[]): ReplayDrawing => ({ view: v, candidates: new Set(candidates), missed: new Set(), bad: new Set() });

describe("replay marks", () => {
  for (const theme of ["light", "dark"] as const) {
    it(`an unread neighbour is a dashed ring, never solid, in ${theme}`, () => {
      const { ctx, strokes } = recorder();
      drawReplayMark(ctx, "n", 0, 0, 10, 1, 1, drawing(view([["r", "read"]]), ["n"]), COLORS[theme]);
      const dashed = strokes.filter((s) => s.dash.length > 0);
      expect(dashed).toHaveLength(1);
      // the only solid stroke is the underlay in the canvas background, which sits under the dashes
      for (const s of strokes.filter((x) => x.dash.length === 0)) expect(s.style).toContain(theme === "dark" ? "9, 9, 11" : "255, 255, 255");
      expect(strokes.indexOf(dashed[0]!)).toBeGreaterThan(0);
    });

    it(`stays dashed when the page is dimmed or the zoom is small, in ${theme}`, () => {
      const { ctx, strokes } = recorder();
      drawReplayMark(ctx, "n", 0, 0, 10, 0.4, LIT_DIM[theme], drawing(view([["r", "read"]]), ["n"]), COLORS[theme]);
      expect(strokes.some((s) => s.dash.length === 2 && (s.dash[0] ?? 0) > 0)).toBe(true);
    });
  }

  it("a page that is not a candidate gets no dashed ring", () => {
    const { ctx, strokes } = recorder();
    drawReplayMark(ctx, "n", 0, 0, 10, 1, 1, drawing(view([["n", "read"]]), []), COLORS.dark);
    expect(strokes.some((s) => s.dash.length > 0)).toBe(false);
  });

  it("the rest dims further on the dark canvas than on the light one", () => {
    expect(LIT_DIM.dark).toBeLessThan(LIT_DIM.light);
  });
});
