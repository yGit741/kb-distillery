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
});
