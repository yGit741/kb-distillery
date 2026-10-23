import { fromLegacy, legacyTypeToModel } from "./legacyModel";

describe("legacy -> model translation", () => {
  it.each([
    ["paper", "source", "paper"],
    ["ai-chat", "source", "ai-chat"],
    ["book", "collection", "book"],
    ["series", "collection", "series"],
    ["theme", "concept", "topic"],
    ["concept", "concept", "idea"],
    ["question", "concept", "question"],
    ["person", "concept", "person"],
  ])("%s -> %s/%s", (old, type, kind) => {
    expect(legacyTypeToModel(old)).toEqual({ type, kind });
  });
  it("flags drafts and drops non-pages", () => {
    expect(legacyTypeToModel("distilled-think")).toMatchObject({ draft: true });
    expect(legacyTypeToModel("scope")).toBeNull();
    expect(legacyTypeToModel(undefined)).toBeNull();
  });
  it("carries depth for sources only", () => {
    expect(fromLegacy({ type: "paper", depth: "full" })?.depth).toBe("full");
    expect(fromLegacy({ type: "paper", "digestion-status": "deep" })?.depth).toBe("deep");
    expect(fromLegacy({ type: "theme", depth: "full" })?.depth).toBeUndefined();
    expect(fromLegacy({ type: "paper", depth: "bogus" })?.depth).toBeUndefined();
  });
});
