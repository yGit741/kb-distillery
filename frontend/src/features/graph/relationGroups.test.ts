import { relationGroups, relationIndex } from "./relationGroups";
import { slugResolver, cellIds } from "./tools/QueryPanel";
import { node } from "./fixtures";
import { degreeOf, type GRelation } from "./types";

const r = (source: string, target: string, kind: string, origin = "computed", note = ""): GRelation => ({ source, target, kind, origin, note });

describe("relationGroups", () => {
  const byId = new Map(["a", "b", "c"].map((id) => [id, node(id)] as const));

  it("groups both ends by kind, stated kinds first, one row per page and kind", () => {
    const idx = relationIndex([r("a", "b", "mentions"), r("b", "a", "mentions"), r("c", "a", "student-of"), r("a", "c", "student-of", "stored", "PhD"), r("a", "zz", "extends", "stored")]);
    const g = relationGroups("a", idx, byId, degreeOf);
    expect(g.map((x) => [x.kind, x.computed, x.rows.map((y) => [y.page.id, y.note])])).toEqual([
      ["student-of", false, [["c", "PhD"]]],
      ["mentions", true, [["b", ""]]],
    ]);
  });

  it("no relations: no groups", () => {
    expect(relationGroups("a", relationIndex([]), byId, degreeOf)).toEqual([]);
  });
});

describe("query cells", () => {
  it("resolve bare slugs, also against <kb>:<slug> ids when unique, and lists of slugs", () => {
    const byId = new Map(["x:a", "x:b", "y:b", "c"].map((id) => [id, node(id)] as const));
    const resolve = slugResolver(byId);
    expect(cellIds("c", resolve)).toEqual(["c"]);
    expect(cellIds("a", resolve)).toEqual(["x:a"]);
    expect(cellIds("b", resolve)).toEqual([]);
    expect(cellIds(["a", "c", 3], resolve)).toEqual(["x:a", "c"]);
  });
});
