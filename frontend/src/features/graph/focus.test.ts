import { buildNeighborMap } from "./graphData";
import { computeFocus, linkOpacity, nodeOpacity } from "./focus";

const nb = buildNeighborMap([{ source: "a", target: "b" }, { source: "b", target: "c" }]);

describe("focus", () => {
  it("is off with nothing hovered or selected, or when disabled", () => {
    expect(computeFocus(new Set(), null, nb, true)).toBeNull();
    expect(computeFocus(new Set(["a"]), "b", nb, false)).toBeNull();
  });
  it("covers the selection and the hovered node together, plus neighbours", () => {
    const f = computeFocus(new Set(["a"]), "c", nb, true);
    expect([...(f?.core ?? [])].sort()).toEqual(["a", "c"]);
    expect([...(f?.lit ?? [])].sort()).toEqual(["a", "b", "c"]);
  });
  it("dims everything else", () => {
    const f = computeFocus(new Set(["a"]), null, nb, true);
    expect(nodeOpacity("a", f)).toBe(1);
    expect(nodeOpacity("b", f)).toBe(0.95);
    expect(nodeOpacity("c", f)).toBe(0.12);
    expect(nodeOpacity("c", null)).toBe(1);
  });
  it("lifts links at the focus and fades the rest; shared links are fainter", () => {
    const f = computeFocus(new Set(["a"]), null, nb, true);
    expect(linkOpacity("a", "b", f, 0.35, "wikilink")).toBeCloseTo(0.7);
    expect(linkOpacity("b", "c", f, 0.35, "wikilink")).toBeCloseTo(0.0525);
    expect(linkOpacity("x", "y", null, 0.5, "shared")).toBeCloseTo(0.3);
  });
});
