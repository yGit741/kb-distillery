import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { ago } from "./api";
import { applySpec, captureSpec, suggestName } from "./viewSpec";

beforeEach(() => {
  useGraphUi.setState({ ...DEFAULT_PREFS, shownTypes: undefined, shownDepths: null, hiddenKeys: new Set(), view: null });
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
