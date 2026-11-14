import { describe, expect, it } from "vitest";
import { node } from "../fixtures";
import { buildNeighborMap } from "../graphData";
import { fedConcepts, kindDetail, kindLine, sourceKinds, sourceState } from "./model";

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
];
const neighbors = buildNeighborMap(links);
const byId = new Map(nodes.map((n) => [n.id, n] as const));
const support = new Map([["idea-a", 3], ["idea-b", 1], ["topic-c", 1]]);

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
  });

  it("inside a kind: busiest source first, least supported concept first, idle sources apart", () => {
    const d = kindDetail("paper", nodes, neighbors, byId, support);
    expect(d.sources.map((s) => [s.node.id, s.concepts.slice().sort()])).toEqual([
      ["p-two", ["idea-a", "idea-b"]],
      ["p-used", ["idea-a", "jane"]],
    ]);
    // a person is not counted for support, so people close the list whatever their count
    expect(d.concepts.map((c) => [c.node.id, c.support])).toEqual([
      ["idea-b", 1],
      ["idea-a", 3],
      ["jane", 0],
    ]);
    expect(d.waiting.map((n) => n.id)).toEqual(["p-waiting"]);
    expect(d.unlinked.map((n) => n.id)).toEqual(["p-loose"]);
  });

  it("says the open issues in words", () => {
    expect(kindLine({ waiting: 8, unlinked: 3 })).toBe("8 waiting, 3 feed no concept");
    expect(kindLine({ waiting: 0, unlinked: 1 })).toBe("1 feed no concept");
    expect(kindLine({ waiting: 0, unlinked: 0 })).toBe("all in use");
  });
});
