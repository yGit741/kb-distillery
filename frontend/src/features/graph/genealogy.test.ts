import { describe, expect, it } from "vitest";
import { genealogyOf } from "./genealogy";

const n = (id: string, y = 2020) => ({ id, title: id.toUpperCase(), year: y, citationCount: 3 });
// a -> b -> c -> d (cites), e cites a, f cites e, g cites f
const g = {
  nodes: ["a", "b", "c", "d", "e", "f", "g", "x"].map((id) => n(id)),
  links: [["a", "b"], ["b", "c"], ["c", "d"], ["e", "a"], ["f", "e"], ["g", "f"], ["a", "x"]].map(([source, target]) => ({ source: source as string, target: target as string })),
};
const all = () => true;

describe("genealogyOf", () => {
  it("walks two hops each way from the focus and labels every role", () => {
    const r = genealogyOf(g, "a", all);
    expect(r).not.toBeNull();
    const roles = Object.fromEntries((r?.nodes ?? []).map((x) => [x.id, x.role]));
    expect(roles).toEqual({ a: "focus", b: "cited", c: "cited", x: "cited", e: "citing", f: "citing" });
    expect(r?.cited).toBe(3);
    expect(r?.citing).toBe(2);
    expect(r?.links.some((l) => l.source === "c" && l.target === "d")).toBe(false);
  });

  it("keeps source papers only", () => {
    const r = genealogyOf(g, "a", (id) => id !== "b");
    expect(r?.nodes.map((x) => x.id)).not.toContain("b");
    expect(r?.nodes.map((x) => x.id)).not.toContain("c");
  });

  it("is null without citation data for the focus", () => {
    expect(genealogyOf(g, "nope", all)).toBeNull();
  });
});
