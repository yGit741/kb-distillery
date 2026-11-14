import { drawSourceCount } from "./countDraw";

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
  it("caps a long count at 99+", () => {
    const { ctx, calls } = fakeCtx();
    drawSourceCount(ctx, 0, 0, 10, 240, 1, colors);
    expect(calls[1]).toBe("fill:99+");
  });
});
