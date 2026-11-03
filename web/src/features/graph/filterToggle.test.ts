import { node } from "./fixtures";
import { predicateFn } from "./publicPredicate";
import { computeVisible } from "./rules";
import { useGraphUi } from "./store";
import { colorKey } from "./style";

// no reset: this is the state a first-time visitor (empty localStorage) opens the graph in
const FRESH = useGraphUi.getState();
const ALL = ["topic", "idea", "paper", "article"];

const nodes = [
  node("t1", { type: "topic", maturity: "seed" }),
  node("i1", { type: "idea", maturity: "seed", inDegree: 2 }),
  node("i2", { type: "idea", maturity: "growing", inDegree: 1 }),
  node("i-orphan", { type: "idea", maturity: "seed" }),
  node("p-deep", { type: "paper", layer: "source", depth: "deep", maturity: "seed" }),
  node("p-listed", { type: "paper", layer: "source", depth: "listed", maturity: "seed" }),
];

/** What GraphScreen computes from the store (colour by Status). */
const count = () => {
  const s = useGraphUi.getState();
  return computeVisible(nodes, {
    shownTypes: s.shownTypes === undefined ? new Set(ALL) : s.shownTypes,
    shownDepths: s.shownDepths,
    search: "",
    rules: [],
    restrict: null,
    force: false,
    revealed: new Set(),
    keep: predicateFn(s.predicate),
    hiddenKeys: s.hiddenKeys,
    keyOf: (n) => colorKey(n, "status"),
  }).size;
};

describe("a legend chip clicked twice is the identity, from the default state", () => {
  beforeEach(() => useGraphUi.setState({ ...FRESH, colorBy: "status", hiddenKeys: new Set() }));

  it("starts on the Map view's public-pages filter", () => {
    expect(FRESH.predicate).toBe("public");
    expect(count()).toBe(4);
  });
  it("colour key row", () => {
    const before = count();
    useGraphUi.getState().toggleKey("seed");
    expect(count()).toBeLessThan(before);
    useGraphUi.getState().toggleKey("seed");
    expect(count()).toBe(before);
  });
  it("type chip", () => {
    const before = count();
    useGraphUi.getState().toggleType("idea", ALL, ALL);
    useGraphUi.getState().toggleType("idea", ALL, ALL);
    expect(count()).toBe(before);
  });
  it("layer and depth chips", () => {
    const before = count();
    useGraphUi.getState().setLayerTypes(["paper"], false, ALL, ALL);
    useGraphUi.getState().setLayerTypes(["paper"], true, ALL, ALL);
    useGraphUi.getState().toggleDepth("deep", ["listed", "deep"]);
    useGraphUi.getState().toggleDepth("deep", ["listed", "deep"]);
    expect(count()).toBe(before);
  });
  it("only its own chip (or Show all) drops the public-pages filter", () => {
    useGraphUi.setState({ predicate: null });
    expect(count()).toBe(6);
  });
});
