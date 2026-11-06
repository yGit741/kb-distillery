import { describe, expect, it } from "vitest";
import type { ToolStep } from "@/features/chat/sse";
import { candidatesOf, hasReplay, marksContext, replaySteps, viewAt } from "./replay";

const trace: ToolStep[] = [
  { name: "Grep", summary: "grep rank", seen: ["a", "b", "c"] },
  { name: "Read", summary: "read a", read: ["a"] },
  { name: "Bash", summary: "no pages here" },
  { name: "Read", summary: "read b", read: ["b"] },
];

describe("replay trail", () => {
  it("only steps with page data can be scrubbed to", () => {
    expect(replaySteps(trace).map((t) => t.summary)).toEqual(["grep rank", "read a", "read b"]);
    expect(hasReplay(trace)).toBe(true);
    expect(hasReplay([{ name: "Bash", summary: "x" }])).toBe(false);
    expect(hasReplay(undefined)).toBe(false);
  });

  it("each step adds to the trail: seen, then read, then cited at the end", () => {
    const steps = replaySteps(trace);
    const first = viewAt(steps, 0, ["c", "z"]);
    expect([...first.roles]).toEqual([["a", "seen"], ["b", "seen"], ["c", "cited"]]); // a cited page shows once it is in the trail
    expect(first.atEnd).toBe(false);
    expect(first.path).toEqual([]);
    const mid = viewAt(steps, 1, []);
    expect(mid.roles.get("a")).toBe("read");
    expect([...mid.current]).toEqual(["a"]);
    const end = viewAt(steps, 2, ["z"]);
    expect(end.roles.get("z")).toBe("cited");
    expect(end.path).toEqual([["a", "b"]]);
    expect(end.atEnd).toBe(true);
    expect(viewAt(steps, 99, []).atEnd).toBe(true);
  });
});

describe("pages one link away, not read", () => {
  const nb = new Map<string, string[]>([
    ["a", ["b", "x", "y", "z"]],
    ["b", ["a", "x", "y", "w"]],
    ["c", ["x"]],
  ]);
  const all = new Set(["a", "b", "c", "x", "y", "z", "w"]);
  it("ranks by how many read pages link to them, then by slug", () => {
    expect(candidatesOf(["a", "b"], nb, new Set(), all)).toEqual(["x", "y", "w", "z"]);
  });
  it("skips read, listed and hidden pages and caps at five", () => {
    expect(candidatesOf(["a", "b"], nb, new Set(["x"]), new Set(["y", "z", "w"]))).toEqual(["y", "w", "z"]);
    const wide = new Map([["a", ["1", "2", "3", "4", "5", "6", "7"]]]);
    expect(candidatesOf(["a"], wide, new Set(), new Set(["1", "2", "3", "4", "5", "6", "7"]))).toEqual(["1", "2", "3", "4", "5"]);
  });
});

describe("marks as context", () => {
  it("missed and bad become one line each", () => {
    expect(marksContext(["p", "q"], ["r"], (s) => s.toUpperCase())).toBe("Also read: P, Q\nRe-check these citations: R");
    expect(marksContext([], [], (s) => s)).toBe("");
    expect(marksContext([], ["r"], (s) => s)).toBe("Re-check these citations: r");
  });
});
