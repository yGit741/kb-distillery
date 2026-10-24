import { gapOf, pickMagnetic, reachOf, REACH_MAX, REACH_MIN, type ScreenNode } from "./magnet";

const n = (id: string, x: number, y: number, r = 5): ScreenNode => ({ id, x, y, r });

describe("magnetic pointer", () => {
  it("picks the node under the pointer", () => {
    const list = [n("a", 0, 0), n("b", 100, 0)];
    expect(pickMagnetic(list, 1, 1)).toBe("a");
  });
  it("pulls the nearest node when the pointer is a little off, within its reach", () => {
    const list = [n("a", 0, 0), n("b", 200, 0)];
    expect(pickMagnetic(list, 30, 0)).toBe("a");
    expect(pickMagnetic(list, 100, 400)).toBeNull();
  });
  it("reach follows how crowded the node is, clamped", () => {
    const crowded = [n("a", 0, 0), n("b", 12, 0)];
    const sparse = [n("a", 0, 0), n("b", 1000, 0)];
    expect(reachOf(crowded[0] as ScreenNode, crowded)).toBe(REACH_MIN);
    expect(reachOf(sparse[0] as ScreenNode, sparse)).toBe(REACH_MAX);
    const only = n("only", 0, 0);
    expect(gapOf(only, [only])).toBe(40);
  });
  it("keeps the current target until another is clearly closer", () => {
    const list = [n("a", 0, 0, 10), n("b", 40, 0, 10)];
    // slightly nearer to b, but a is the sticky target
    expect(pickMagnetic(list, 22, 0, "a")).toBe("a");
    expect(pickMagnetic(list, 22, 0, null)).toBe("b");
    // clearly on b: switch
    expect(pickMagnetic(list, 40, 0, "a")).toBe("b");
  });
  it("returns null for an empty graph", () => {
    expect(pickMagnetic([], 0, 0)).toBeNull();
  });
  it("leave band: a current target is kept a little past its reach (no flicker at the edge)", () => {
    const list = [n("a", 0, 0), n("b", 1000, 0)];
    const reach = REACH_MAX; // sparse: the clamp
    const x = 5 + reach * 1.15; // past the reach, inside LEAVE x reach
    expect(pickMagnetic(list, x, 0, null)).toBeNull();
    expect(pickMagnetic(list, x, 0, "a")).toBe("a");
  });
});
