import { describe, expect, it } from "vitest";
import { rimLayout } from "./citationRim";

const papers = [
  ...Array.from({ length: 20 }, (_, i) => ({ id: `a${i}`, degree: i < 5 ? 2 : 0 })),
  ...Array.from({ length: 8 }, (_, i) => ({ id: `b${i}`, degree: i < 2 ? 1 : 0 })),
];
const topic = (id: string) => (id.startsWith("a") ? 0 : 1);
const names = new Map([[0, "Learning theory"], [1, "Statistics"]]);

describe("citationRim", () => {
  it("pins every uncited paper, pulls every cited one, never both", () => {
    const r = rimLayout(papers, topic, names, 8);
    expect(r.pins.size).toBe(21);
    expect(r.pull.size).toBe(7);
    for (const id of r.pins.keys()) expect(r.pull.has(id)).toBe(false);
  });

  it("keeps every clump outside the cited papers' pull radius, so the web never runs through a clump", () => {
    const r = rimLayout(papers, topic, names, 8);
    const pullR = Math.max(...[...r.pull.values()].map(([x, y]) => Math.hypot(x, y)));
    const clumpMin = Math.min(...[...r.pins.values()].map(([x, y]) => Math.hypot(x, y)));
    expect(clumpMin).toBeGreaterThan(pullR + 8);
  });

  it("packs a clump without overlap: no two pins closer than one dot", () => {
    const r = rimLayout(papers, topic, names, 8);
    const p = [...r.pins.values()];
    p.forEach(([ax, ay], i) => p.slice(i + 1).forEach(([bx, by]) => expect(Math.hypot(ax - bx, ay - by)).toBeGreaterThan(8 * 0.9)));
  });

  it("labels each topic with its name and paper count", () => {
    const r = rimLayout(papers, topic, names, 8);
    expect(r.labels.map((l) => [l.name, l.count])).toEqual([["Learning theory", 20], ["Statistics", 8]]);
  });
});
