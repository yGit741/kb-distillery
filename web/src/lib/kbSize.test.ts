import { describe, expect, it } from "vitest";
import { bySize, kbProblem, kbScore } from "./kbSize";

const s = (concepts: number, edges: number, sources = 0) => ({ concepts, sources, edges });

describe("kbSize", () => {
  it("scores the mean of concepts and concept edges", () => {
    expect(kbScore(s(27, 51, 97))).toBe(39);
  });

  it("flags almost no concepts and concepts with no links", () => {
    expect(kbProblem(s(4, 6))).toBe("only 4 concepts");
    expect(kbProblem(s(12, 0))).toBe("no links between concepts");
    expect(kbProblem(s(1, 0))).toBe("only 1 concept, no links between concepts");
    expect(kbProblem(s(13, 10))).toBeNull();
  });

  it("sorts largest first and keeps rows with no size last, in their order", () => {
    const rows = [{ id: "x" }, { id: "small" }, { id: "y" }, { id: "big" }];
    const size = { small: s(4, 6), big: s(100, 400) } as Record<string, ReturnType<typeof s>>;
    expect(bySize(rows, (r) => size[r.id]).map((r) => r.id)).toEqual(["big", "small", "x", "y"]);
  });
});
