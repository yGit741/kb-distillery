import { countAnchor, drawSourceCount } from "./countDraw";

const colors = { background: "#fff", muted: "#888", font: "sans-serif" } as Parameters<typeof drawSourceCount>[6];

function fakeCtx() {
  const calls: string[] = [];
  const ctx = { save: () => {}, restore: () => {}, strokeText: (t: string) => calls.push(`stroke:${t}`), fillText: (t: string) => calls.push(`fill:${t}`) } as unknown as CanvasRenderingContext2D;
  return { ctx, calls };
}

describe("the source count on a concept", () => {
  it("writes the number over a halo in the canvas colour", () => {
    const { ctx, calls } = fakeCtx();
    drawSourceCount(ctx, 0, 0, 10, 3, 1, colors);
    expect(calls).toEqual(["stroke:3", "fill:3"]);
    expect(ctx.fillStyle).toBe("#888");
    expect(ctx.strokeStyle).toBe("#fff");
  });
  it("sits outside the mark at every size: clear of the ring, to the upper right, under a label above it", () => {
    const size = 9.5;
    for (const r of [6, 12, 30, 80]) {
      const at = countAnchor(100, 100, r, size);
      const dist = Math.hypot(at.x - 100, at.y - 100);
      expect(dist - r).toBeCloseTo(size * 0.9); // the same clear gap whatever the mark's size
      expect(at.x).toBeGreaterThan(100 + r * 0.8); // to the right
      expect(at.y).toBeLessThan(100); // above the centre
      expect(at.y).toBeGreaterThan(100 - r - size / 2); // its centre never climbs past the mark's top by half its height
    }
  });
  it("is written where the anchor says", () => {
    const at: number[] = [];
    const ctx = { save: () => {}, restore: () => {}, strokeText: () => {}, fillText: (_t: string, x: number, y: number) => at.push(x, y) } as unknown as CanvasRenderingContext2D;
    drawSourceCount(ctx, 5, 7, 10, 3, 2, colors);
    const want = countAnchor(5, 7, 10, 9.5 / 2);
    expect(at).toEqual([want.x, want.y]);
  });
  it("caps a long count at 99+", () => {
    const { ctx, calls } = fakeCtx();
    drawSourceCount(ctx, 0, 0, 10, 240, 1, colors);
    expect(calls[1]).toBe("fill:99+");
  });
});
