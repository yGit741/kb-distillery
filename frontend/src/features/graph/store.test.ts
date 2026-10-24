import { DEFAULT_PREFS, loadPrefs, savePrefs, useGraphUi } from "./store";

const ALL = ["paper", "course", "topic", "idea", "person"];
const DEFAULTS = ["topic", "idea"];

beforeEach(() => {
  localStorage.clear();
  useGraphUi.setState({ ...DEFAULT_PREFS, shownTypes: undefined, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, fitTick: 0 });
});

describe("type visibility", () => {
  it("starts from the schema default (concepts, people off) and toggles from there", () => {
    useGraphUi.getState().toggleType("person", ALL, DEFAULTS);
    expect([...(useGraphUi.getState().shownTypes ?? [])].sort()).toEqual(["idea", "person", "topic"]);
    useGraphUi.getState().toggleType("topic", ALL, DEFAULTS);
    expect([...(useGraphUi.getState().shownTypes ?? [])].sort()).toEqual(["idea", "person"]);
  });
  it("turning every type on is stored as null (no filter)", () => {
    useGraphUi.getState().setLayerTypes(["paper", "course", "person"], true, ALL, DEFAULTS);
    expect(useGraphUi.getState().shownTypes).toBeNull();
  });
  it("hides a whole layer", () => {
    useGraphUi.setState({ shownTypes: null });
    useGraphUi.getState().setLayerTypes(["paper"], false, ALL, DEFAULTS);
    expect(useGraphUi.getState().shownTypes?.has("paper")).toBe(false);
    expect(useGraphUi.getState().shownTypes?.has("topic")).toBe(true);
  });
  it("depth filter returns to null when all depths are back", () => {
    const depths = ["listed", "easy", "full", "deep"];
    useGraphUi.getState().toggleDepth("listed", depths);
    expect(useGraphUi.getState().shownDepths?.has("listed")).toBe(false);
    useGraphUi.getState().toggleDepth("listed", depths);
    expect(useGraphUi.getState().shownDepths).toBeNull();
  });
});

describe("sources, rules, labels", () => {
  it("reveals and hides a set of sources together", () => {
    useGraphUi.getState().toggleReveal(["a", "b"]);
    expect([...useGraphUi.getState().revealed]).toEqual(["a", "b"]);
    useGraphUi.getState().toggleReveal(["a", "b"]);
    expect(useGraphUi.getState().revealed.size).toBe(0);
    useGraphUi.getState().toggleReveal(["a"]);
    useGraphUi.getState().toggleReveal(["a", "b"]);
    expect(useGraphUi.getState().revealed.size).toBe(2);
  });
  it("adds, edits and removes rules", () => {
    const s = useGraphUi.getState();
    s.addRule();
    s.patchRule(0, { value: "paper" });
    expect(useGraphUi.getState().rules[0]).toMatchObject({ field: "type", op: "is", value: "paper" });
    useGraphUi.getState().removeRule(0);
    expect(useGraphUi.getState().rules).toEqual([]);
  });
  it("toggles per-type labels and the flyout", () => {
    useGraphUi.getState().toggleTypeLabels("paper");
    expect(useGraphUi.getState().typeLabels.has("paper")).toBe(true);
    useGraphUi.getState().openFlyout("filter");
    useGraphUi.getState().openFlyout("filter");
    expect(useGraphUi.getState().flyout).toBeNull();
  });
  it("reset clears every filter", () => {
    useGraphUi.setState({ search: "x", shownTypes: null, revealed: new Set(["a"]) });
    useGraphUi.getState().resetFilters();
    expect(useGraphUi.getState()).toMatchObject({ search: "", shownTypes: undefined });
  });
});

describe("preferences", () => {
  it("round-trips settings and ignores values of the wrong type", () => {
    savePrefs({ ...DEFAULT_PREFS, nodeSize: 8, colorBy: "depth" });
    expect(loadPrefs()).toMatchObject({ nodeSize: 8, colorBy: "depth" });
    localStorage.setItem("kb-graph-prefs-v1", JSON.stringify({ nodeSize: "big", magnet: false }));
    expect(loadPrefs()).toMatchObject({ nodeSize: DEFAULT_PREFS.nodeSize, magnet: false });
  });
  it("survives broken storage", () => {
    localStorage.setItem("kb-graph-prefs-v1", "{nope");
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
  });
  it("saves a changed preference but not view state", () => {
    useGraphUi.getState().set({ nodeSize: 9 });
    expect(JSON.parse(localStorage.getItem("kb-graph-prefs-v1") ?? "{}").nodeSize).toBe(9);
    localStorage.clear();
    useGraphUi.getState().set({ search: "zzz" });
    expect(localStorage.getItem("kb-graph-prefs-v1")).toBeNull();
  });
});
