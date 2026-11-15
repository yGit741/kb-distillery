import { liveEdgeStory, withStoryEdges } from "./storyEdges";
import type { GNode } from "./types";
import { storyById } from "./lab/views";

describe("liveEdgeStory", () => {
  it("names the edge view while its own types are drawn", () => {
    expect(liveEdgeStory("citations", new Set(["paper"]), storyById)).toBe("citations");
  });
  it("stays on while every type is drawn (null)", () => {
    expect(liveEdgeStory("citations", null, storyById)).toBe("citations");
  });
  it("is empty once other types are drawn (a left-over Citations id must not empty the Concepts view)", () => {
    expect(liveEdgeStory("citations", new Set(["topic", "idea"]), storyById)).toBe("");
    expect(liveEdgeStory("citations", undefined, storyById)).toBe("");
  });
  it("is empty without an edge story or for a view that draws no relation", () => {
    expect(liveEdgeStory("", new Set(["paper"]), storyById)).toBe("");
    expect(liveEdgeStory("map", new Set(["paper"]), storyById)).toBe("");
  });
});

describe("withStoryEdges", () => {
  const nodes = [{ id: "a" }, { id: "b" }, { id: "c" }] as GNode[];
  const relations = [
    { source: "a", target: "b", kind: "cites", origin: "computed", note: "" },
    { source: "b", target: "c", kind: "builds_on", origin: "stored", note: "" },
  ];
  it("draws a citation as cites, and any other relation as related with its own kind kept for the lit edge's words", () => {
    const out = withStoryEdges({ nodes, links: [], relations }, { edges: ["cites", "builds_on"] });
    expect(out.links).toEqual([
      { source: "a", target: "b", kind: "cites" },
      { source: "b", target: "c", kind: "related", rel: "builds_on" },
    ]);
  });
});
