import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { ago } from "./api";
import { withFlag } from "@/flags/testing";
import { EMPTY_STACK, makeLayer, type ViewStack } from "../../layers/model";
import { useLayers } from "../../layers/store";
import { applySpec, captureSpec, suggestName, type ViewSpecV2 } from "./viewSpec";

beforeEach(() => {
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, shownDepths: null, hiddenKeys: new Set(), view: null });
});

describe("a pinned view's spec", () => {
  it("round-trips the drawn types, the colouring and the hidden colours (sets become arrays)", () => {
    useGraphUi.setState({ story: "", colorBy: "depth", shownTypes: new Set(["idea", "topic"]), hiddenKeys: new Set(["Deep"]) });
    const spec = captureSpec(useGraphUi.getState());
    expect(JSON.parse(JSON.stringify(spec))).toMatchObject({ v: 1, story: "", colorBy: "depth", types: ["idea", "topic"], hiddenKeys: ["Deep"] });
    useGraphUi.setState({ colorBy: "area", shownTypes: null, hiddenKeys: new Set() });
    const deps = { applyView: vi.fn(), showPicked: vi.fn() };
    expect(applySpec(JSON.parse(JSON.stringify(spec)), deps)).toBe(true);
    const s = useGraphUi.getState();
    expect(s.colorBy).toBe("depth");
    expect([...(s.shownTypes ?? [])].sort()).toEqual(["idea", "topic"]);
    expect(s.hiddenKeys.has("Deep")).toBe(true);
    expect(deps.applyView).not.toHaveBeenCalled();
  });

  it("a named view goes through the screen's own path first, the rest on top", () => {
    const deps = { applyView: vi.fn(), showPicked: vi.fn() };
    applySpec({ v: 1, story: "map", types: "all" }, deps);
    expect(deps.applyView).toHaveBeenCalledWith("map");
    expect(useGraphUi.getState().shownTypes).toBeNull();
  });

  it("the pages of a picked view come back through showPicked", () => {
    const deps = { applyView: vi.fn(), showPicked: vi.fn() };
    applySpec({ v: 1, pages: ["a", "b"] }, deps);
    expect(deps.showPicked).toHaveBeenCalledWith(["a", "b"]);
  });

  it("a restore replaces the pages on screen instead of adding to them", () => {
    useGraphUi.setState({ view: { kind: "picked", label: "old", hits: new Set(["x"]), shown: new Set(["x"]) } });
    const deps = { applyView: vi.fn(), showPicked: vi.fn() };
    applySpec({ v: 1, types: "all" }, deps);
    expect(useGraphUi.getState().view).toBeNull();
    useGraphUi.setState({ view: { kind: "picked", label: "old", hits: new Set(["x"]), shown: new Set(["x"]) } });
    applySpec({ v: 1, pages: ["a"] }, deps);
    expect(useGraphUi.getState().view).toBeNull(); // showPicked then builds the new one from nothing
    expect(deps.showPicked).toHaveBeenCalledWith(["a"]);
  });

  it("a spec of another shape is left alone and reported as not applied", () => {
    const deps = { applyView: vi.fn(), showPicked: vi.fn() };
    expect(applySpec({ cypher: "MATCH (n) RETURN n" }, deps)).toBe(false);
  });

  it("names the view after its story or its pages, else says untitled", () => {
    expect(suggestName({ story: "", view: null })).toBe("Untitled view");
    expect(suggestName({ story: "map", view: null })).toBe("Map");
  });
});

describe("ago", () => {
  const now = Date.parse("2026-11-04T12:00:00Z");
  it("says it in a few plain words", () => {
    expect(ago("2026-11-04T11:59:30Z", now)).toBe("just now");
    expect(ago("2026-11-04T11:30:00Z", now)).toBe("30 min ago");
    expect(ago("2026-11-04T07:00:00Z", now)).toBe("5 h ago");
    expect(ago("2026-11-03T07:00:00Z", now)).toBe("yesterday");
    expect(ago("2026-10-25T12:00:00Z", now)).toBe("10 d ago");
    expect(ago(undefined, now)).toBe("");
  });
});

describe("a pinned view as a layer stack (graph-intent)", () => {
  const deps = () => ({ applyView: vi.fn(), showPicked: vi.fn() });
  const stackOf = (...texts: string[]): ViewStack => ({ v: 2, layers: texts.map((t) => makeLayer("show", "nodes", { nodes: [{ t: "degree", op: ">=", n: 8 }] }, t)) });
  beforeEach(() => useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null }));

  it("captureSpec writes { v: 2, layers, text } from a stack with layers, and the V1 knobs otherwise", () => {
    const spec = captureSpec(useGraphUi.getState(), stackOf("Hubs", "Recent"));
    expect(spec).toMatchObject({ v: 2, text: "Hubs · Recent" });
    expect((spec as ViewSpecV2).layers).toHaveLength(2);
    expect(captureSpec(useGraphUi.getState(), EMPTY_STACK)).toMatchObject({ v: 1 });
    expect(captureSpec(useGraphUi.getState())).toMatchObject({ v: 1 });
  });

  it("applySpec puts a v2 spec on the stack as a replace, with fresh ids", async () => {
    await withFlag("graph-intent", true, async () => {
      const spec = JSON.parse(JSON.stringify(captureSpec(useGraphUi.getState(), stackOf("Hubs"))));
      expect(applySpec(spec, deps())).toBe(true);
      const layers = useLayers.getState().stack.layers;
      expect(layers.map((l) => l.text)).toEqual(["Hubs"]);
      expect(layers[0]!.id).not.toBe(spec.layers[0].id);
      expect(useLayers.getState().history).toHaveLength(1);
    });
  });

  it("a V1 pin applies as one legacy layer named like the pin, drawn through the V1 path", async () => {
    await withFlag("graph-intent", true, async () => {
      const applyLegacy = vi.fn();
      useLayers.getState().setGraph({ nodes: [], links: [], show: vi.fn(), applyLegacy });
      const d = deps();
      expect(applySpec({ v: 1, story: "", types: "all" }, d, { name: "My old view" })).toBe(true);
      const layers = useLayers.getState().stack.layers;
      expect(layers).toHaveLength(1);
      expect(layers[0]!.text).toBe("My old view");
      expect(layers[0]!.legacy).toMatchObject({ types: "all" });
      expect(applyLegacy).toHaveBeenCalledWith(expect.objectContaining({ types: "all" }));
    });
  });

  it("a V1 spec with nothing recognisable is reported as not applied", async () => {
    await withFlag("graph-intent", true, async () => {
      useLayers.getState().setGraph({ nodes: [], links: [], show: vi.fn(), applyLegacy: vi.fn() });
      expect(applySpec({ v: 1 }, deps(), { name: "x" })).toBe(false);
      expect(useLayers.getState().stack.layers).toHaveLength(0);
    });
  });

  it("flag off: a v2 spec is not understood and V1 applies to the knobs exactly as before", async () => {
    await withFlag("graph-intent", false, async () => {
      expect(applySpec({ v: 2, layers: [makeLayer("show", "nodes", {}, "x")], text: "x" }, deps())).toBe(false);
      expect(useLayers.getState().stack.layers).toHaveLength(0);
      expect(applySpec({ v: 1, colorBy: "depth" }, deps(), { name: "old" })).toBe(true);
      expect(useGraphUi.getState().colorBy).toBe("depth");
      expect(useLayers.getState().stack.layers).toHaveLength(0);
    });
  });
});
