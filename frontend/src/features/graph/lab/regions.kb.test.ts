import { areaNames, regionKey, regionsOf } from "./regions";
import type { GNode } from "../types";

const node = (id: string, kb: string, area: string, x: number): GNode & { x: number; y: number } =>
  ({ id: `${kb}:${id}`, kb, slug: id, label: id, title: id, type: "idea", layer: "concept", status: "", depth: "", areas: [area],
     inDegree: 0, outDegree: 0, path: "", added: "", changed: "", preview: "", properties: {}, x, y: 0 }) as GNode & { x: number; y: number };

describe("regions by knowledge base", () => {
  const nodes = [0, 1, 2].flatMap((i) => [node(`a${i}`, "alpha", "x", i), node(`b${i}`, "beta", "x", 100 + i)]);

  it("one knowledge base: regions are areas", () => {
    const names = areaNames(nodes, [{ id: "alpha", name: "Alpha" }]);
    expect(regionKey(nodes[0]!, names)).toBe("x");
  });

  it("several: one region per knowledge base, named after it", () => {
    const names = areaNames(nodes, [{ id: "alpha", name: "Alpha" }, { id: "beta", name: "Beta" }]);
    const regions = regionsOf(nodes, names);
    expect(regions.map((r) => r.name).sort()).toEqual(["Alpha", "Beta"]);
    expect(regions.find((r) => r.name === "Beta")!.x).toBe(101);
  });
});
