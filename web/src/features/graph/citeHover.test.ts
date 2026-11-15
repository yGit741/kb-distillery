import { describe, expect, it } from "vitest";
import { drawEdges, pickCite } from "./citeHover";
import { readCanvasColors } from "./canvasTheme";
import type { SimLink, SimNode } from "./types";

const node = (id: string, x: number, y: number) => ({ id, x, y }) as SimNode;
const link = (a: SimNode, b: SimNode) => ({ source: a, target: b, kind: "cites" }) as unknown as SimLink;
// two horizontal citations 20 units apart, straight (no control points)
const top = link(node("a", 0, 0), node("b", 100, 0));
const low = link(node("c", 0, 20), node("d", 100, 20));

describe("pickCite", () => {
  it("enters only within 6 px of an edge", () => {
    expect(pickCite([top, low], null, 50, 7, 1)).toBeNull();
    expect(pickCite([top, low], null, 50, 5, 1)).toBe(top);
  });
  it("holds the edge until the pointer is beyond 12 px (hysteresis)", () => {
    expect(pickCite([top, low], top, 50, 9, 1)).toBe(top);
    expect(pickCite([top, low], top, 50, 13, 1)).toBeNull(); // past 12 from the edge, and 7 from the other (over 6)
  });
  it("switches to another edge only when it is clearly closer", () => {
    expect(pickCite([top, low], top, 50, 11, 1)).toBe(top);
    expect(pickCite([top, low], top, 50, 15, 1)).toBe(low);
  });
  it("scales the bands with the zoom (pixels on screen)", () => {
    expect(pickCite([top, low], null, 50, 5, 2)).toBeNull();
    expect(pickCite([top, low], null, 50, 2.5, 2)).toBe(top);
  });
});

describe("pickCite with any kind of edge (flag edge-select)", () => {
  const wiki = { ...top, kind: "wikilink" } as SimLink;
  const any = (l: SimLink) => l.kind !== "pile-page";
  it("by default only a citation lights up", () => {
    expect(pickCite([wiki], null, 50, 2, 1)).toBeNull();
  });
  it("with an accept rule, the nearest accepted edge does", () => {
    expect(pickCite([wiki, low], null, 50, 2, 1, any)).toBe(wiki);
    expect(pickCite([wiki, low], null, 50, 18, 1, any)).toBe(low);
  });
  it("an edge far from the pointer is skipped without being measured, the held one still counts", () => {
    const far = link(node("e", 1000, 1000), node("f", 1100, 1000));
    expect(pickCite([far, top], null, 50, 3, 1, any)).toBe(top);
    expect(pickCite([far, top], top, 50, 11, 1, any)).toBe(top);
  });
});

describe("drawEdges", () => {
  /** a canvas context that records the text it writes */
  function recorder() {
    const texts: string[] = [];
    const noop = () => {};
    const ctx = new Proxy({} as Record<string, unknown>, {
      get: (t, k) => (k === "fillText" ? (s: string) => texts.push(s) : k === "measureText" ? (s: string) => ({ width: s.length * 6 }) : k in t ? t[k as string] : noop),
      set: (t, k, v) => ((t[k as string] = v), true),
    });
    return { ctx: ctx as unknown as CanvasRenderingContext2D, texts };
  }
  const titled = (id: string, x: number, y: number) => ({ ...node(id, x, y), title: `Title ${id}` }) as SimNode;

  it("writes each edge's words and each page's full title once, however many lit edges touch it", () => {
    const hub = titled("hub", 0, 0);
    const a = titled("a", 200, 100);
    const b = titled("b", -200, 100);
    const l1 = { source: hub, target: a, kind: "wikilink" } as SimLink;
    const l2 = { source: b, target: hub, kind: "shared", shared: 2 } as SimLink;
    const { ctx, texts } = recorder();
    drawEdges(ctx, [l1, l2], 1, readCanvasColors(), () => 5, (l) => (l.kind === "shared" ? "2 shared sources" : "links to"), () => true);
    expect(texts.filter((t) => t === "Title hub")).toHaveLength(1);
    expect(texts).toEqual(expect.arrayContaining(["links to", "2 shared sources", "Title a", "Title b"]));
  });
});
