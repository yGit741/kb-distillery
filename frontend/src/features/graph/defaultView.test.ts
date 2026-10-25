import { initialView, withDefaultView } from "./defaultView";

describe("initialView", () => {
  it("prefers the URL's view", () => {
    expect(initialView("thesis", { view: "map" })).toBe("thesis");
  });
  it("falls back to the snapshot's home.view when the URL has none", () => {
    expect(initialView(undefined, { view: "map" })).toBe("map");
  });
  it("is nothing without either, or with an unknown id", () => {
    expect(initialView(undefined, undefined)).toBeUndefined();
    expect(initialView(undefined, { view: null })).toBeUndefined();
    expect(initialView(undefined, { view: "no-such-view" })).toBeUndefined();
    expect(initialView("bogus", { view: "map" }, () => false)).toBeUndefined();
  });
  it("reads globalThis.KB_EMBEDDED by default", () => {
    globalThis.KB_EMBEDDED = { home: { view: "map" } } as never;
    try {
      expect(initialView(undefined)).toBe("map");
    } finally {
      globalThis.KB_EMBEDDED = undefined;
    }
  });
});

describe("withDefaultView", () => {
  it("adds ?view= to Home graph links only when the blob sets one", () => {
    expect(withDefaultView({ pages: "a,b" }, { view: "map" })).toEqual({ pages: "a,b", view: "map" });
    expect(withDefaultView({ pages: "a,b" }, undefined)).toEqual({ pages: "a,b" });
    expect(withDefaultView({ view: "thesis" }, { view: "map" })).toEqual({ view: "thesis" });
  });
});
