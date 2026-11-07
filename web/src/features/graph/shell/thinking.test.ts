import type { ToolStep } from "@/features/chat/sse";
import { kindOf, popSources, roundsOf, rolesOf, summaryOf, thinkingOf, liveStatus, linkKey } from "./thinking";

const TRACE: ToolStep[] = [
  { id: "a", name: "mcp", summary: "shortlist", round: 1, kind: "shortlist", query: "margin bound", seen: ["idea-margin", "topic-learning-theory", "2019-fine-grained"], status: "done" },
  { id: "b", name: "Read", summary: "read idea-margin", round: 2, kind: "open", read: ["idea-margin"], status: "done" },
  { id: "c", name: "Read", summary: "read paper", round: 2, kind: "raw", read: ["2019-fine-grained"], status: "done" },
  { id: "d", name: "WebSearch", summary: "web", round: 3, kind: "web-search", query: "margin theory", domains: ["arxiv.org", "x.com"], status: "done" },
  { id: "e", name: "WebFetch", summary: "fetch", round: 3, kind: "web-source", url: "https://www.openreview.net/forum?id=1", status: "done" },
];
const ANSWER = "See [Margin](idea-margin.md) and [Theory](topic-learning-theory.md), again [Margin](idea-margin.md).";

describe("show my thinking: pure parts", () => {
  it("groups calls sent together into rounds; old steps without a round are one round each", () => {
    expect(roundsOf(TRACE).map((r) => r.steps.length)).toEqual([1, 2, 2]);
    expect(roundsOf([{ name: "Grep", summary: "x" }, { name: "Read", summary: "y" }]).map((r) => r.n)).toEqual([1, 2]);
    expect(kindOf({ name: "WebSearch", summary: "" })).toBe("web-search");
    expect(kindOf({ name: "Grep", summary: "" })).toBe("keyword");
  });

  it("numbers citations by first appearance, counts, opened-not-cited, missable and the web source", () => {
    const t = thinkingOf(TRACE, ANSWER);
    expect([...t.citeNo]).toEqual([["idea-margin", 1], ["topic-learning-theory", 2]]);
    expect(summaryOf(t)).toBe("2 opened · 3 found · 1 web search");
    expect(t.openedNotCited).toEqual(["2019-fine-grained"]);
    expect(t.missable).toEqual([]);
    expect(t.webSources).toEqual([{ id: "web:https://www.openreview.net/forum?id=1", url: "https://www.openreview.net/forum?id=1", host: "openreview.net", about: ["idea-margin", "2019-fine-grained"] }]);
  });

  it("the live word", () => {
    expect(liveStatus([{ name: "Read", summary: "", status: "running" }], "")).toBe("looking");
    expect(liveStatus([], "")).toBe("deciding");
    expect(liveStatus([], "Not")).toBe("writing the answer");
  });

  it("a source read in full pops with links to the answer's glowing pages only", () => {
    const roles = rolesOf(thinkingOf(TRACE, ANSWER), true);
    const layer: Record<string, string> = { "2019-fine-grained": "source", "idea-margin": "concept", "topic-learning-theory": "concept", "idea-other": "concept" };
    const nb = new Map([["2019-fine-grained", ["idea-margin", "idea-other", "topic-learning-theory"]]]);
    const drawn = new Set(["idea-margin", "topic-learning-theory", "idea-other"]);
    const { pop, links } = popSources(roles, (id) => layer[id], drawn, nb);
    expect(pop).toEqual(["2019-fine-grained"]);
    expect([...links].sort()).toEqual([linkKey("2019-fine-grained", "idea-margin"), linkKey("2019-fine-grained", "topic-learning-theory")].sort());
    // an undigested raw read carries no source slug: nothing pops
    const raw = rolesOf(thinkingOf([{ name: "explore_raw", summary: "read raw/x.pdf", kind: "raw", query: "raw/x.pdf" }], ""), true);
    expect(popSources(raw, (id) => layer[id], drawn, nb).pop).toEqual([]);
  });
});
