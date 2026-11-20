import { describe, expect, it } from "vitest";
import { MAX_WORDED_EDGES, wordedEdges } from "./edgeWords";
import type { SimLink } from "./types";

const link = (i: number, kind: string, rel?: string) => ({ source: `a${i}`, target: `b${i}`, kind, ...(rel ? { rel } : {}) }) as SimLink;
const none = new Set<string>();

describe("wordedEdges", () => {
  it("words every edge of a sparse graph with two edge types or more", () => {
    const links = [link(1, "related", "calls"), link(2, "related", "includes"), link(3, "related", "calls")];
    expect(wordedEdges(links, none)).toHaveLength(3);
  });

  it("words nothing when every edge is of one type", () => {
    expect(wordedEdges([link(1, "related", "calls"), link(2, "related", "calls")], none)).toEqual([]);
    expect(wordedEdges([link(1, "wikilink"), link(2, "wikilink")], none)).toEqual([]);
  });

  it("words nothing on a dense graph", () => {
    const links = Array.from({ length: MAX_WORDED_EDGES + 1 }, (_, i) => link(i, i % 2 ? "wikilink" : "shared"));
    expect(wordedEdges(links, none)).toEqual([]);
  });

  it("leaves out hidden kinds and the data layer's pile connectors, and counts types over what is left", () => {
    const links = [link(1, "wikilink"), link(2, "shared"), link(3, "pile-page")];
    expect(wordedEdges(links, new Set(["shared"]))).toEqual([]);
    expect(wordedEdges(links, none).map((l) => l.kind)).toEqual(["wikilink", "shared"]);
  });
});
