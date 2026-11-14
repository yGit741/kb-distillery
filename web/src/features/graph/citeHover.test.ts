import { describe, expect, it } from "vitest";
import { pickCite } from "./citeHover";
import type { SimLink, SimNode } from "./types";

const node = (id: string, x: number, y: number) => ({ id, x, y }) as SimNode;
const link = (a: SimNode, b: SimNode) => ({ source: a, target: b, kind: "cites" }) as unknown as SimLink;
// two horizontal citations 20 units apart, straight (no control points)
const top = link(node("a", 0, 0), node("b", 100, 0));
const low = link(node("c", 0, 20), node("d", 100, 20));

describe("pickCite", () => {
  it("enters only within 6 px of an edge", () => {
    expect(pickCite([top, low], null, 50, 7, 1)).toBeNull();
    expect(pickCite([top, low], null, 50, 5, 1)).toBe(top);
  });
  it("holds the edge until the pointer is beyond 12 px (hysteresis)", () => {
    expect(pickCite([top, low], top, 50, 9, 1)).toBe(top);
    expect(pickCite([top, low], top, 50, 13, 1)).toBeNull(); // past 12 from the edge, and 7 from the other (over 6)
  });
  it("switches to another edge only when it is clearly closer", () => {
    expect(pickCite([top, low], top, 50, 11, 1)).toBe(top);
    expect(pickCite([top, low], top, 50, 15, 1)).toBe(low);
  });
  it("scales the bands with the zoom (pixels on screen)", () => {
    expect(pickCite([top, low], null, 50, 5, 2)).toBeNull();
    expect(pickCite([top, low], null, 50, 2.5, 2)).toBe(top);
  });
});
