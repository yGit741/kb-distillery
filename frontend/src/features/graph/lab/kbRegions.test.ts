import { formatKbs, parseKbs } from "@/lib/kbSelection";
import { kbAnchors, kbGroups, kbLabelSpot, KB_PAD } from "./kbRegions";
import type { SimNode } from "../types";

const n = (id: string, kb: string, x: number, y: number) => ({ id, kb, x, y }) as unknown as SimNode;

describe("kb regions", () => {
  it("anchors sit in a row, in order, far enough apart not to overlap", () => {
    const a = kbAnchors(["alpha", "beta"], new Map([["alpha", 1000], ["beta", 25]]), 40);
    const [ax] = a.get("alpha")!;
    const [bx] = a.get("beta")!;
    expect(ax).toBeLessThan(bx);
    const ra = Math.sqrt(1000) * 40 * 0.55 + KB_PAD;
    const rb = Math.sqrt(25) * 40 * 0.55 + KB_PAD;
    expect(bx - ax).toBeGreaterThan(ra + rb);
  });

  it("groups positioned nodes by knowledge base and names each region above its top", () => {
    const g = kbGroups([n("a", "alpha", 0, 10), n("b", "alpha", 100, -20), n("c", "beta", 5, 5), { id: "d", kb: "beta" } as SimNode]);
    expect(g.get("alpha")!.length).toBe(2);
    expect(g.get("beta")!.length).toBe(1);
    expect(kbLabelSpot(g.get("alpha")!)).toEqual({ x: 50, top: -20 - KB_PAD });
  });
});

describe("?kbs= param", () => {
  it("absent = default, none = nothing, else ids", () => {
    expect(parseKbs(undefined)).toBeNull();
    expect(parseKbs("none")).toEqual([]);
    expect(parseKbs("a,b,a")).toEqual(["a", "b"]);
    expect(formatKbs([], "a")).toBe("none");
    expect(formatKbs(["a"], "a")).toBeUndefined();
    expect(formatKbs(["a", "b"], "a")).toBe("a,b");
  });
});
