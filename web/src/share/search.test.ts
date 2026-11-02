import { describe, expect, it } from "vitest";
import { makeFixtureBlob } from "./fixture";
import { findPaths, searchPages } from "./search";

// Behaviour of the in-browser search and shortest paths over a baked blob.
// (The differential test against the retired kb-static.js shim was removed with the shim.)
describe("searchPages", () => {
  const fixture = makeFixtureBlob();

  it("honours limit", () => {
    expect(searchPages(fixture, "rank", 2).hits).toHaveLength(2);
    expect(searchPages(fixture, "rank", 2).total).toBe(searchPages(fixture, "rank").total);
  });

  it("ranks title hits above body hits and breaks ties by id", () => {
    const hits = searchPages(fixture, "rank").hits;
    expect(hits.slice(0, 2).map((h) => h.id)).toEqual(["tensor-rank", "matrix-rank"]);
    expect(hits.find((h) => h.id === "island")!.score).toBeLessThan(hits[1]!.score);
    expect(hits.map((h) => h.score)).toEqual([...hits.map((h) => h.score)].sort((a, b) => b - a));
  });

  it("falls back to the card preview when no line matches outside headings and tables", () => {
    const r = searchPages(fixture, "tensor-rank");
    expect(r.hits.find((h) => h.id === "tensor-rank")?.snippet).toBe("preview of tensor-rank");
  });
});

describe("findPaths", () => {
  const fixture = makeFixtureBlob();

  it("answers null for unknown pages and distance null for an island", () => {
    expect(findPaths(fixture, "tensor-rank", "no-such-page")).toBeNull();
    expect(findPaths(fixture, "island", "tensor-rank")).toEqual({ a: "island", b: "tensor-rank", distance: null, paths: [] });
  });

  it("returns at most four shortest paths with directed hops and contexts", () => {
    const r = findPaths(fixture, "course-learning-theory", "2019-implicit-regularization")!;
    expect(r.distance).toBe(2);
    expect(r.paths.length).toBeLessThanOrEqual(4);
    expect(r.paths[0]!.hops[0]).toMatchObject({ dir: "forward" });
  });
});
