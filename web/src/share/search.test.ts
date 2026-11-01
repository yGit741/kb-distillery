import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { ShareBlob } from "./blob";
import { makeFixtureBlob, makeRandomBlob } from "./fixture";
import { findPaths, searchPages } from "./search";

/**
 * Differential test: the TypeScript port must answer exactly what the legacy static shim answered.
 * The shim (src/kb_distillery/share/static/kb-static.js) is evaluated as-is with the blob as its data.
 * Delete this file together with the shim when the legacy share pages go.
 */
// vitest runs with the package dir (web/) as cwd
const SHIM = resolve(process.cwd(), "../src/kb_distillery/share/static/kb-static.js");

interface Legacy {
  search(q: string, limit?: number): unknown;
  findPaths(a: string, b: string): unknown;
}

let legacy: Legacy;
const w = window as unknown as { KB_DATA?: ShareBlob; KB_STATIC?: Legacy };

function loadLegacy(blob: ShareBlob): Legacy {
  // The shim memoises adjacency on the data object (`__adj`): give it a private deep copy.
  w.KB_DATA = JSON.parse(JSON.stringify(blob)) as ShareBlob;
  (0, eval)(readFileSync(SHIM, "utf8"));
  return w.KB_STATIC!;
}

const QUERIES = ["rank", "Rank", "  rank  ", "tensor rank", "rank tensor", "cp", "decomposition", "np-hard", "vc dimension", "r", "", "zzzz-nothing", "[[", "quote about", "|", "island", "page"];

describe("searchPages == legacy shim", () => {
  const fixture = makeFixtureBlob();
  beforeAll(() => {
    legacy = loadLegacy(fixture);
  });

  it.each(QUERIES)("query %j", (q) => {
    expect(searchPages(fixture, q)).toEqual(legacy.search(q));
  });

  it("honours limit and caps it at 5000, like the shim", () => {
    expect(searchPages(fixture, "rank", 2)).toEqual(legacy.search("rank", 2));
    expect(searchPages(fixture, "rank", 2).hits).toHaveLength(2);
    expect(searchPages(fixture, "rank", 2).total).toBe(searchPages(fixture, "rank").total);
  });

  it("ranks title hits above body hits and breaks ties by id", () => {
    const hits = searchPages(fixture, "rank").hits;
    expect(hits.slice(0, 2).map((h) => h.id)).toEqual(["tensor-rank", "matrix-rank"]);   // title + slug hits first
    expect(hits.find((h) => h.id === "island")!.score).toBeLessThan(hits[1]!.score);       // body-only hit
    expect(hits.map((h) => h.score)).toEqual([...hits.map((h) => h.score)].sort((a, b) => b - a));
  });

  it("falls back to the card preview when no line matches outside headings and tables", () => {
    const r = searchPages(fixture, "tensor-rank");
    expect(r.hits.find((h) => h.id === "tensor-rank")?.snippet).toBe("preview of tensor-rank");
  });
});

describe("findPaths == legacy shim", () => {
  const fixture = makeFixtureBlob();
  beforeAll(() => {
    legacy = loadLegacy(fixture);
  });

  const PAIRS: [string, string][] = [
    ["tensor-rank", "matrix-rank"],
    ["matrix-rank", "cp-decomposition"],
    ["course-learning-theory", "2019-implicit-regularization"],
    ["lecture-01-pac", "tensor-rank"],
    ["tensor-rank", "tensor-rank"],
    ["island", "tensor-rank"],
    ["tensor-rank", "no-such-page"],
    ["no-such-page", "tensor-rank"],
  ];
  it.each(PAIRS)("%s -> %s", (a, b) => {
    expect(findPaths(fixture, a, b)).toEqual(legacy.findPaths(a, b));
  });

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

describe("randomised vault", () => {
  const big = makeRandomBlob();
  beforeAll(() => {
    legacy = loadLegacy(big);
  });

  it("matches the shim on 40 queries", () => {
    const qs = ["rank", "tensor gradient", "fourier", "page-1", "boolean entropy", "kernel margin bound", "width", "depth loss", "nothing-here", "init norm"];
    for (const q of qs) for (const limit of [undefined, 5, 40]) expect(searchPages(big, q, limit)).toEqual(legacy.search(q, limit));
  });

  it("matches the shim on 60 path pairs", () => {
    const slugs = Object.keys(big.pages);
    for (let i = 0; i < 60; i++) {
      const a = slugs[(i * 7) % slugs.length]!;
      const b = slugs[(i * 13 + 5) % slugs.length]!;
      expect(findPaths(big, a, b)).toEqual(legacy.findPaths(a, b));
    }
  });
});
