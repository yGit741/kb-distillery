import { describe, expect, it } from "vitest";
import { node } from "../fixtures";
import { buildNeighborMap } from "../graphData";
import { fedConcepts, kindLine, kindPages, sourceKinds, sourceState } from "./model";

const src = (id: string, type: string, depth: string) => node(id, { type, layer: "source", depth });
const nodes = [
  src("p-used", "paper", "full"),
  src("p-waiting", "paper", "listed"),
  src("p-loose", "paper", "easy"),
  src("p-two", "pdf", "deep"),
  src("v-used", "lecture", "full"),
  src("l-used", "lecture", "full"),
  node("idea-a", { type: "idea" }),
  node("idea-b", { type: "idea" }),
  node("topic-c"),
  node("jane", { type: "person" }),
];
const links = [
  { source: "p-used", target: "idea-a" },
  { source: "idea-b", target: "p-two" },
  { source: "p-two", target: "idea-a" },
  { source: "p-loose", target: "v-used" }, // a source only: still feeds no concept
  { source: "v-used", target: "idea-a" },
  { source: "l-used", target: "topic-c" },
  { source: "p-used", target: "jane" },
  { source: "p-waiting", target: "topic-c" }, // a stub's link: the source is still waiting
];
const neighbors = buildNeighborMap(links);
const byId = new Map(nodes.map((n) => [n.id, n] as const));

describe("health by source kind", () => {
  it("puts every source in exactly one state", () => {
    expect(sourceState(byId.get("p-waiting")!, neighbors, byId)).toBe("waiting");
    expect(sourceState(byId.get("p-loose")!, neighbors, byId)).toBe("unlinked");
    expect(sourceState(byId.get("p-used")!, neighbors, byId)).toBe("healthy");
    // no depth at all reads as listed, as the depth colouring does
    expect(sourceState(src("x", "paper", ""), neighbors, byId)).toBe("waiting");
  });

  it("groups types that share an icon, largest kind first, and the states add up", () => {
    const kinds = sourceKinds(nodes, neighbors, byId);
    expect(kinds.map((k) => [k.kind, k.label, k.total, k.waiting, k.unlinked, k.healthy])).toEqual([
      ["paper", "Papers", 4, 1, 1, 2], // a paper and a pdf share the page icon
      ["play", "Lectures", 2, 0, 0, 2], 
    ]);
    for (const k of kinds) expect(k.waiting + k.unlinked + k.healthy).toBe(k.total);
  });

  it("a knowledge base without sources has no kinds", () => {
    expect(sourceKinds([node("idea-a")], new Map(), new Map())).toEqual([]);
  });

  it("names the concepts a kind feeds", () => {
    expect([...fedConcepts("paper", nodes, neighbors, byId)].sort()).toEqual(["idea-a", "idea-b", "jane"]);
    expect([...fedConcepts("play", nodes, neighbors, byId)].sort()).toEqual(["idea-a", "topic-c"]);
    expect(fedConcepts("mail", nodes, neighbors, byId).size).toBe(0);
    // topic-c is linked from a waiting paper only: papers do not feed it yet, on the dial or on the map
    expect(fedConcepts("paper", nodes, neighbors, byId).has("topic-c")).toBe(false);
    expect(kindPages("paper", nodes, neighbors, byId)).not.toContain("topic-c");
  });

  it("a pressed kind is its digested sources and what they feed; a waiting source is left out", () => {
    expect(kindPages("paper", nodes, neighbors, byId).sort()).toEqual(["idea-a", "idea-b", "jane", "p-loose", "p-two", "p-used"]);
    expect(kindPages("play", nodes, neighbors, byId).sort()).toEqual(["idea-a", "l-used", "topic-c", "v-used"]);
    expect(kindPages("mail", nodes, neighbors, byId)).toEqual([]);
  });

  it("says the open issues in words", () => {
    expect(kindLine({ waiting: 8, unlinked: 3 })).toBe("8 waiting, 3 feed no concept");
    expect(kindLine({ waiting: 0, unlinked: 1 })).toBe("1 feed no concept");
    expect(kindLine({ waiting: 0, unlinked: 0 })).toBe("all in use");
  });
});
