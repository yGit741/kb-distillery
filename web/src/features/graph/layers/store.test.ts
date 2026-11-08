import { useKb } from "@/lib/store";
import { sampleLinks, sampleNodes } from "../fixtures";
import { useShellStore } from "../shell/shellStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { EMPTY_STACK, makeLayer, type Layer } from "./model";
import { HISTORY_MAX, sentenceLayer, useLayers } from "./store";

const show = (text: string, nodes: NonNullable<Layer["subgraph"]["nodes"]>) => makeLayer("show", "nodes", { nodes }, text);
const papers = () => show("papers", [{ t: "type", value: "paper" }]);
const shown = vi.fn((ids: string[]) => useGraphUi.setState({ view: { kind: "picked", label: "picked", hits: new Set(ids), shown: new Set(ids) } }));
const applyLegacy = vi.fn();

beforeEach(() => {
  shown.mockClear();
  applyLegacy.mockClear();
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], preview: null, graph: { nodes: sampleNodes, links: sampleLinks, show: shown, applyLegacy } });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, hiddenKeys: new Set(), hiddenLinkKinds: new Set(), shownTypes: undefined });
  useKb.getState().clearSelection();
  useShellStore.setState({ shape: null, undo: null });
});

describe("layer store", () => {
  it("apply draws the shown pages and keeps the stack", () => {
    useLayers.getState().apply("replace", [papers()]);
    expect(shown).toHaveBeenLastCalledWith(["2019-fine-grained", "2020-listed-paper"]);
    expect(useLayers.getState().stack.layers.map((l) => l.text)).toEqual(["papers"]);
    expect(useLayers.getState().history).toHaveLength(1);
  });

  it("a replaced view is one step back", () => {
    const { apply, undo, redo } = useLayers.getState();
    apply("replace", [papers()]);
    apply("replace", [show("ideas", [{ t: "type", value: "idea" }])]);
    expect(useLayers.getState().stack.layers.map((l) => l.text)).toEqual(["ideas"]);
    expect(undo()).toBe(true);
    expect(useLayers.getState().stack.layers.map((l) => l.text)).toEqual(["papers"]);
    expect([...useGraphUi.getState().view!.hits]).toEqual(["2019-fine-grained", "2020-listed-paper"]);
    expect(redo()).toBe(true);
    expect(useLayers.getState().stack.layers.map((l) => l.text)).toEqual(["ideas"]);
    expect([...useGraphUi.getState().view!.hits]).toEqual(["idea-margin"]);
    expect(undo() && undo()).toBe(true);
    expect(useLayers.getState().stack.layers).toHaveLength(0);
    expect(useGraphUi.getState().view).toBeNull();
    expect(undo()).toBe(false);
  });

  it("a new change empties the redo list", () => {
    const { apply, undo } = useLayers.getState();
    apply("replace", [papers()]);
    undo();
    expect(useLayers.getState().future).toHaveLength(1);
    apply("replace", [papers()]);
    expect(useLayers.getState().future).toHaveLength(0);
  });

  it("keeps at most twenty steps", () => {
    for (let i = 0; i < HISTORY_MAX + 5; i++) useLayers.getState().apply("stack", [show(`s${i}`, [{ t: "type", value: "idea" }])]);
    expect(useLayers.getState().history).toHaveLength(HISTORY_MAX);
  });

  it("stack adds on top and remove by text takes a layer away, drawing the rest", () => {
    const { apply } = useLayers.getState();
    apply("replace", [papers()]);
    apply("stack", [show("people", [{ t: "type", value: "person" }])]);
    expect(shown).toHaveBeenLastCalledWith(["2019-fine-grained", "2020-listed-paper", "jane-doe"]);
    expect(apply("remove", "people")).toBe(true);
    expect(shown).toHaveBeenLastCalledWith(["2019-fine-grained", "2020-listed-paper"]);
    expect(apply("remove", "no such chip")).toBe(false);
    expect(useLayers.getState().history).toHaveLength(3);
  });

  it("removing the last restricting layer draws every page again", () => {
    const { apply } = useLayers.getState();
    apply("replace", [papers()]);
    apply("remove", "papers");
    expect(useGraphUi.getState().view).toBeNull();
  });

  it("a style layer drives the knobs, and removing it gives the old value back", () => {
    const { apply } = useLayers.getState();
    const before = useGraphUi.getState().colorBy;
    apply("stack", [makeLayer("style", "nodes", {}, "colour by area", { style: { color: "area" } })]);
    expect(useGraphUi.getState().colorBy).toBe("area");
    apply("remove", "colour by area");
    expect(useGraphUi.getState().colorBy).toBe(before);
  });

  it("hidden link kinds are drawn off, and come back with the layer gone", () => {
    const { apply } = useLayers.getState();
    apply("stack", [makeLayer("hide", "edges", { edges: [{ t: "type", value: "MENTIONS" }] }, "hide mentions")]);
    expect([...useGraphUi.getState().hiddenLinkKinds].sort()).toEqual(["related", "wikilink"]);
    apply("remove", "hide mentions");
    expect(useGraphUi.getState().hiddenLinkKinds.size).toBe(0);
  });

  it("edit changes a layer in place and draws again", () => {
    const l = show("near", [{ t: "hops", of: "course-runi-rl", n: 1 }]);
    useLayers.getState().apply("replace", [l]);
    expect(shown).toHaveBeenLastCalledWith(["course-runi-rl", "2019-fine-grained"]);
    useLayers.getState().edit(l.id, { ...l, subgraph: { nodes: [{ t: "hops", of: "course-runi-rl", n: 2 }] } });
    expect(shown.mock.lastCall![0]).toHaveLength(4);
  });

  it("a change by hand retires the applied state", () => {
    useLayers.getState().apply("stack", [makeLayer("style", "nodes", {}, "", { style: { color: "area" } })]);
    const applied = useLayers.getState().applied!;
    expect(applied.colorBy).toBe("area");
    useGraphUi.setState({ colorBy: "depth" });
    expect(useGraphUi.getState().colorBy).not.toBe(applied.colorBy);
  });

  it("recordDrawn remembers a sentence drawn elsewhere, and undo restores the knobs from before it", () => {
    const before = { ...useGraphUi.getState(), selection: [] as string[] };
    const snap = { view: before.view, shownTypes: before.shownTypes, colorBy: before.colorBy, sizeBy: before.sizeBy, layoutMode: before.layoutMode, story: before.story, hiddenKeys: before.hiddenKeys, hiddenLinkKinds: before.hiddenLinkKinds, selection: [] };
    useGraphUi.setState({ colorBy: "depth" });
    useLayers.getState().recordDrawn("replace", [sentenceLayer("colour by depth")], snap);
    expect(useLayers.getState().stack.layers.map((l) => l.text)).toEqual(["colour by depth"]);
    expect(shown).not.toHaveBeenCalled();
    useLayers.getState().undo();
    expect(useGraphUi.getState().colorBy).toBe(before.colorBy);
    expect(useLayers.getState().stack.layers).toHaveLength(0);
  });

  it("clear drops every layer in one undoable step", () => {
    const { apply, clear, undo } = useLayers.getState();
    apply("replace", [papers()]);
    apply("stack", [show("people", [{ t: "type", value: "person" }])]);
    clear();
    expect(useLayers.getState().stack.layers).toHaveLength(0);
    undo();
    expect(useLayers.getState().stack.layers).toHaveLength(2);
  });

  it("a legacy layer applies through applySpec's path", () => {
    const spec = { v: 1, story: "map" };
    useLayers.getState().apply("replace", [makeLayer("show", "nodes", {}, "Orphans", { legacy: spec as never })]);
    expect(applyLegacy).toHaveBeenCalledWith(spec);
    expect(shown).not.toHaveBeenCalled();
  });
});

describe("a style layer alone", () => {
  it("keeps every page drawn and the story (its page types) in place", () => {
    useGraphUi.setState({ story: "orient" });
    useLayers.getState().apply("replace", [makeLayer("style", "nodes", {}, "colour by depth", { style: { color: "depth" } })]);
    expect(shown).not.toHaveBeenCalled();
    expect(useGraphUi.getState().view).toBeNull();
    expect(useGraphUi.getState().colorBy).toBe("depth");
    expect(useGraphUi.getState().story).toBe("orient");
  });

  it("stacked onto a show layer, the shown set stays", () => {
    useLayers.getState().apply("replace", [papers()]);
    useLayers.getState().apply("stack", [makeLayer("style", "nodes", {}, "colour by depth", { style: { color: "depth" } })]);
    expect(shown).toHaveBeenLastCalledWith(["2019-fine-grained", "2020-listed-paper"]);
    expect(useGraphUi.getState().colorBy).toBe("depth");
  });
});

describe("preview", () => {
  it("setPreview leaves the stack alone and cancel gives back a tint", () => {
    const style = makeLayer("style", "nodes", {}, "colour by depth", { style: { color: "depth" } });
    expect(useLayers.getState().setPreview("stack", [style])).toBe(true);
    const p = useLayers.getState().preview!;
    expect(p.lines).toEqual(["style nodes color by depth"]);
    expect(p.ids).toBeNull();
    expect(useGraphUi.getState().colorBy).toBe("depth");
    expect(useLayers.getState().stack.layers).toHaveLength(0);
    useLayers.getState().cancelPreview();
    expect(useGraphUi.getState().colorBy).toBe(DEFAULT_PREFS.colorBy);
    expect(useLayers.getState().preview).toBeNull();
  });

  it("commitPreview applies once, as one undo step", () => {
    useLayers.getState().setPreview("replace", [papers()]);
    expect(useLayers.getState().preview!.count).toBe(2);
    expect(useLayers.getState().commitPreview()).toBe(true);
    expect(useLayers.getState().preview).toBeNull();
    expect(useLayers.getState().stack.layers).toHaveLength(1);
    expect(useLayers.getState().history).toHaveLength(1);
  });
});

describe("editing a layer in place", () => {
  it("is one undo step and the knobs follow", () => {
    const { apply, edit, undo } = useLayers.getState();
    apply("stack", [makeLayer("style", "nodes", {}, "colour by depth", { style: { color: "depth" } })]);
    const l = useLayers.getState().stack.layers[0]!;
    edit(l.id, { ...l, style: { color: "type" } });
    expect(useLayers.getState().history).toHaveLength(2);
    expect(useGraphUi.getState().colorBy).toBe("type");
    undo();
    expect(useGraphUi.getState().colorBy).toBe("depth");
  });
});
