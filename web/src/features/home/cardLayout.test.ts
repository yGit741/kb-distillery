import { FIT_PAD_X, FIT_PAD_Y, fitToBox, placeCardLabels, type LabelNode } from "./cardLayout";

const inside = (b: number[], W: number, H: number) => b[0]! >= 0 && b[1]! >= 0 && b[2]! <= W && b[3]! <= H;

describe("card graph layout", () => {
  it("stretches a round layout to fill a wide box, centred", () => {
    const pts = fitToBox(
      [
        { x: -100, y: -100 },
        { x: 100, y: 100 },
        { x: 0, y: 0 },
      ],
      1000,
      330,
    );
    expect(Math.min(...pts.map((p) => p.x))).toBeCloseTo(500 - (330 - 2 * FIT_PAD_Y) * 1.2, 0);
    expect(Math.min(...pts.map((p) => p.y))).toBeCloseTo(FIT_PAD_Y);
    expect(Math.max(...pts.map((p) => p.y))).toBeCloseTo(330 - FIT_PAD_Y);
    expect(pts[2]).toEqual({ x: 500, y: 165 });
    // a wide layout reaches the side padding
    const wide = fitToBox([{ x: 0, y: 0 }, { x: 100, y: 20 }], 1000, 330);
    expect(wide[0]!.x).toBeCloseTo(FIT_PAD_X);
    expect(wide[1]!.x).toBeCloseTo(1000 - FIT_PAD_X);
  });

  it("puts a single node in the centre", () => {
    expect(fitToBox([{ x: 5, y: 7 }], 400, 300)).toEqual([{ x: 200, y: 150 }]);
  });

  it("never clips a label at the edge, never covers a node, never overlaps a label", () => {
    const nodes: LabelNode[] = [
      { id: "left", x: 6, y: 150, r: 6 },
      { id: "right", x: 594, y: 150, r: 6 },
      { id: "a", x: 300, y: 150, r: 14 },
      { id: "b", x: 330, y: 150, r: 8 },
      { id: "c", x: 300, y: 120, r: 8 },
    ];
    const asks = nodes.map((n) => ({ id: n.id, lines: ["Tensor factorization"], w: 120, forced: n.id === "a" }));
    const placed = placeCardLabels(nodes, asks, 600, 300, 14);
    expect(placed.map((p) => p.id)).toContain("left");
    expect(placed.map((p) => p.id)).toContain("a");
    for (const p of placed) {
      expect(inside(p.box, 600, 300)).toBe(true);
      for (const n of nodes) {
        const nx = Math.max(p.box[0], Math.min(n.x, p.box[2]));
        const ny = Math.max(p.box[1], Math.min(n.y, p.box[3]));
        expect((nx - n.x) ** 2 + (ny - n.y) ** 2).toBeGreaterThanOrEqual(n.r ** 2);
      }
      for (const q of placed)
        if (q !== p) expect(p.box[0] < q.box[2] && q.box[0] < p.box[2] && p.box[1] < q.box[3] && q.box[1] < p.box[3]).toBe(false);
    }
  });
});
