import { node } from "../fixtures";
import { areaNames, convexHull, coreHull, regionsOf } from "./regions";

describe("regions", () => {
  const at = (id: string, area: string, x: number, y: number) => ({ ...node(id, { areas: [area], type: "idea" }), x, y });
  it("one region per area with enough pages, named after its topic, at the median", () => {
    const nodes = [
      { ...node("theme-a", { type: "topic", title: "Alpha", areas: ["a"] }), x: 0, y: 0 },
      at("a1", "a", 10, 0),
      at("a2", "a", 20, 0),
      at("b1", "b", 0, 0),
    ];
    const r = regionsOf(nodes, areaNames(nodes));
    expect(r).toHaveLength(1);
    expect(r[0]).toMatchObject({ area: "a", name: "Alpha", x: 10, members: 3 });
  });
  it("hull of a square with an inside point is the four corners", () => {
    expect(convexHull([[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5]])).toHaveLength(4);
  });
  it("the core hull ignores a far stray", () => {
    const pts = [at("1", "a", 0, 0), at("2", "a", 1, 0), at("3", "a", 1, 1), at("4", "a", 0, 1), at("5", "a", 0.5, 0.5), at("far", "a", 100, 100)];
    expect(coreHull(pts).some(([x]) => x === 100)).toBe(false);
  });
  it("the σ rule drops a stray beyond mean + 2σ, keeps a tight group whole, and sigma 0 is the old 70% rule", () => {
    const tight = [at("1", "a", 0, 0), at("2", "a", 2, 0), at("3", "a", 2, 2), at("4", "a", 0, 2), at("5", "a", 1, 1), at("6", "a", 1, 0), at("7", "a", 0, 1), at("8", "a", 2, 1), at("9", "a", 1, 2)];
    const stray = at("far", "a", 60, 60);
    expect(coreHull([...tight, stray]).some(([x]) => x === 60)).toBe(false);
    expect(coreHull(tight)).toHaveLength(4); // every corner kept
    expect(coreHull(tight.slice(0, 4))).toHaveLength(4); // fewer than 5: all count
    // sigma 0: the closest 70% of the ten (d[7] = a corner's 1.41 from the median (1,1)) keep every tight page, the stray is out
    expect(coreHull([...tight, stray], 0.7, 0)).toEqual([[0, 0], [2, 0], [2, 2], [0, 2]]);
  });
});
