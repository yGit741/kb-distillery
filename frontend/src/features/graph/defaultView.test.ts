import { initialView, withDefaultView } from "./defaultView";

describe("initialView", () => {
  it("prefers the URL's view", () => {
    expect(initialView({ view: "thesis" }, { view: "map" })).toBe("thesis");
  });
  it("falls back to the snapshot's home.view on a bare link", () => {
    expect(initialView({}, { view: "map" })).toBe("map");
    expect(initialView({ layer: "concept" }, { view: "map" })).toBe("map");
  });
  it("leaves a dive alone (pages, focus, select, search, scope)", () => {
    for (const k of ["pages", "focus", "select", "search", "scope"]) {
      expect(initialView({ [k]: "x" }, { view: "map" })).toBeUndefined();
    }
    expect(initialView({ pages: "a", view: "thesis" }, { view: "map" })).toBe("thesis");
  });
  it("is nothing without either, or with an unknown id", () => {
    expect(initialView({}, undefined)).toBeUndefined();
    expect(initialView({}, { view: null })).toBeUndefined();
    expect(initialView({}, { view: "no-such-view" })).toBeUndefined();
    expect(initialView({ view: "bogus" }, { view: "map" }, () => false)).toBeUndefined();
  });
  it("reads globalThis.KB_EMBEDDED by default", () => {
    globalThis.KB_EMBEDDED = { home: { view: "map" } } as never;
    try {
      expect(initialView({})).toBe("map");
    } finally {
      globalThis.KB_EMBEDDED = undefined;
    }
  });
});

describe("withDefaultView", () => {
  it("adds ?view= only to bare Home graph links, and only when the blob sets one", () => {
    expect(withDefaultView({ layer: "concept" }, { view: "map" })).toEqual({ layer: "concept", view: "map" });
    expect(withDefaultView({ pages: "a,b" }, { view: "map" })).toEqual({ pages: "a,b" });
    expect(withDefaultView({ focus: "a" }, { view: "map" })).toEqual({ focus: "a" });
    expect(withDefaultView({ layer: "concept" }, undefined)).toEqual({ layer: "concept" });
    expect(withDefaultView({ view: "thesis" }, { view: "map" })).toEqual({ view: "thesis" });
  });
});
