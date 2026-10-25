import { buildNeighborMap } from "./graphData";
import { computeFocus, fadedNodeOpacity, focusKey, linkOpacity, nodeOpacity } from "./focus";

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
  it("a hover alone dims nothing; only a selection dims the rest", () => {
    expect(computeFocus(new Set(), "a", nb, true)).toBeNull();
    expect(nodeOpacity("c", computeFocus(new Set(["a"]), null, nb, true))).toBe(0.12);
  });
  it("cross-fades the rest between foci; the new focus shows at once", () => {
    const a = computeFocus(new Set(["a"]), null, nb, true);
    const c = computeFocus(new Set(["c"]), null, nb, true);
    const far = computeFocus(new Set(["x"]), null, nb, true);
    expect(fadedNodeOpacity("c", c, a, 0)).toBe(1); // lit in the new focus: no wait
    expect(fadedNodeOpacity("a", far, a, 0)).toBe(1); // starts from the old look, not from a flash
    expect(fadedNodeOpacity("a", far, a, 0.5)).toBeGreaterThan(0.12);
    expect(fadedNodeOpacity("a", far, a, 1)).toBe(0.12);
  });
  it("the focus key ignores recomputes that change nothing", () => {
    expect(focusKey(computeFocus(new Set(["a"]), null, nb, true))).toBe(focusKey(computeFocus(new Set(["a"]), null, nb, true)));
    expect(focusKey(null)).toBe("");
  });
});
