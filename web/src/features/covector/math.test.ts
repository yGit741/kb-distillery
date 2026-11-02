import { readouts, slices, stats, toCanvas, SIZE } from "./math";

describe("covector math", () => {
  it("starts at the page's defaults: |v| 5, spacing 0.20, score 10", () => {
    const i = { vx: 3, vy: 4, ux: 2, uy: 1 };
    expect(stats(i)).toEqual({ vLen: 5, spacing: 0.2, score: 10 });
    expect(readouts(i)).toEqual({ vLen: "5.00", spacing: "0.20", score: "10.00" });
  });

  it("a zero generator has infinite spacing and no level lines", () => {
    const i = { vx: 0, vy: 0, ux: 1, uy: 1 };
    expect(readouts(i).spacing).toBe("∞");
    expect(readouts(i).score).toBe("0.00");
    expect(slices(i)).toEqual([]);
  });

  it("draws 81 level lines, k = -40…40, the kernel through the origin", () => {
    const s = slices({ vx: 3, vy: 4, ux: 0, uy: 0 });
    expect(s).toHaveLength(81);
    const kernel = s.find((x) => x.k === 0)!;
    // the line is perpendicular to v and passes through the canvas centre
    const mid = [(kernel.from[0] + kernel.to[0]) / 2, (kernel.from[1] + kernel.to[1]) / 2];
    expect(mid[0]).toBeCloseTo(SIZE / 2);
    expect(mid[1]).toBeCloseTo(SIZE / 2);
    const dx = kernel.to[0] - kernel.from[0];
    const dy = -(kernel.to[1] - kernel.from[1]); // math coordinates (y up)
    expect(dx * 3 + dy * 4).toBeCloseTo(0);
  });

  it("the test vector's score is the number of level lines its tip lies on (u = v/|v|² · k)", () => {
    // u = 0.12 * v for v = (3,4) sits on line k = ω(u) = 0.12 * 25 = 3 along v
    const v = { vx: 3, vy: 4 };
    const u = { ux: 0.36, uy: 0.48 };
    expect(stats({ ...v, ...u }).score).toBeCloseTo(3);
    const line = slices({ ...v, ...u }).find((x) => x.k === 3)!;
    const tip = toCanvas(u.ux, u.uy);
    // tip is on the line: cross product of (to-from) and (tip-from) is ~0
    const cross = (line.to[0] - line.from[0]) * (tip[1] - line.from[1]) - (line.to[1] - line.from[1]) * (tip[0] - line.from[0]);
    expect(Math.abs(cross)).toBeLessThan(1e-6 * 2000);
  });

  it("canvas coordinates flip y", () => {
    expect(toCanvas(1, 1)).toEqual([SIZE / 2 + 50, SIZE / 2 - 50]);
  });
});
