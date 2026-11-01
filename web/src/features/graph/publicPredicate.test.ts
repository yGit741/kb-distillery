import { isPublic, predicateFn } from "./publicPredicate";
import type { GNode } from "./types";

const node = (p: Partial<GNode>): GNode => ({ id: "x", title: "", layer: "concept", type: "idea", areas: [], inDegree: 0, outDegree: 0, ...p }) as GNode;

describe("isPublic", () => {
  it("keeps topics even without links", () => {
    expect(isPublic(node({ type: "topic" }))).toBe(true);
  });
  it("keeps linked concepts and collections, drops orphans", () => {
    expect(isPublic(node({ type: "idea", inDegree: 1 }))).toBe(true);
    expect(isPublic(node({ type: "question", outDegree: 2 }))).toBe(true);
    expect(isPublic(node({ layer: "collection", type: "series", inDegree: 3 }))).toBe(true);
    expect(isPublic(node({ type: "idea" }))).toBe(false);
  });
  it("keeps only sources read in depth", () => {
    expect(isPublic(node({ layer: "source", type: "paper", depth: "deep", inDegree: 4 }))).toBe(true);
    expect(isPublic(node({ layer: "source", type: "paper", depth: "full" }))).toBe(true);
    expect(isPublic(node({ layer: "source", type: "article", depth: "easy", inDegree: 9 }))).toBe(false);
    expect(isPublic(node({ layer: "source", type: "paper", depth: "listed" }))).toBe(false);
  });
  it("never shows aux types", () => {
    expect(isPublic(node({ type: "scope", inDegree: 5 }))).toBe(false);
    expect(isPublic(node({ type: "distilled-think", inDegree: 5 }))).toBe(false);
  });
  it("resolves by id", () => {
    expect(predicateFn("public")).toBe(isPublic);
    expect(predicateFn(null)).toBeNull();
  });
});
