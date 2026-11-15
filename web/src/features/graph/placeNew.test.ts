import { describe, expect, it } from "vitest";
import { NEW_GAP, placeNew, type Spot } from "./placeNew";

const far = (nodes: Spot[]) => {
  let least = Infinity;
  for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) least = Math.min(least, Math.hypot(nodes[i]!.x! - nodes[j]!.x!, nodes[i]!.y! - nodes[j]!.y!));
  return least;
};

describe("placing pages added by hand", () => {
  it("sixty sources added to one concept each get a spot of their own, clear of every drawn page", () => {
    const drawn: Spot[] = [{ id: "idea", x: 0, y: 0 }, { id: "other", x: 60, y: 0 }, { id: "third", x: -40, y: 50 }];
    const added: Spot[] = Array.from({ length: 60 }, (_, i) => ({ id: `s${i}` }));
    const nodes = [...drawn, ...added];
    const placed = placeNew(nodes, added.map((s) => ({ source: s.id, target: "idea" })), new Set(added.map((s) => s.id)));
    expect(placed).toHaveLength(60);
    expect(far(nodes)).toBeGreaterThanOrEqual(NEW_GAP - 1e-6);
    // close to the page they hang from: a compact halo, not a far ring
    expect(Math.max(...added.map((s) => Math.hypot(s.x!, s.y!)))).toBeLessThan(NEW_GAP * 12);
  });

  it("never moves a drawn page, and leaves a page it was not asked about to the layout", () => {
    const nodes: Spot[] = [{ id: "idea", x: 5, y: 7 }, { id: "s1" }, { id: "s2" }, { id: "kept", x: 40, y: 40 }];
    placeNew(nodes, [{ source: "s1", target: "idea" }, { source: "s2", target: "idea" }], new Set(["s1", "kept"]));
    expect(nodes[0]).toEqual({ id: "idea", x: 5, y: 7 });
    expect(nodes[3]).toEqual({ id: "kept", x: 40, y: 40 });
    expect(nodes[1]!.x).toBeDefined();
    expect(nodes[2]!.x).toBeUndefined();
  });

  it("a new page that hangs from another new page is placed after it, in the same step", () => {
    const nodes: Spot[] = [{ id: "idea", x: 0, y: 0 }, { id: "leaf" }, { id: "mid" }];
    const placed = placeNew(nodes, [{ source: "leaf", target: "mid" }, { source: "mid", target: "idea" }], new Set(["leaf", "mid"]));
    expect(placed).toEqual(["mid", "leaf"]);
    expect(Math.hypot(nodes[1]!.x! - nodes[2]!.x!, nodes[1]!.y! - nodes[2]!.y!)).toBeGreaterThanOrEqual(NEW_GAP - 1e-6);
  });

  it("a page with no drawn neighbour is left to the layout; one with two starts between them", () => {
    const nodes: Spot[] = [{ id: "a", x: 0, y: 0 }, { id: "b", x: 200, y: 0 }, { id: "mid" }, { id: "lone" }];
    const placed = placeNew(nodes, [{ source: "mid", target: "a" }, { source: "b", target: "mid" }], new Set(["mid", "lone"]));
    expect(placed).toEqual(["mid"]);
    expect(Math.hypot(nodes[2]!.x! - 100, nodes[2]!.y!)).toBeLessThan(NEW_GAP * 2);
    expect(nodes[3]!.x).toBeUndefined();
  });
});
