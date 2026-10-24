import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildGraphData } from "./graphData";
import { rawSnapshot, sampleSnapshot } from "./fixtures";
import { formatOfPile, isPileId, parseRawLayer, PILE_PAGE_LINK_CAP, pileOf, rawSourcesOf } from "./rawLayer";
import { toModel } from "./types";

describe("data layer", () => {
  it("is absent from a plain snapshot", () => {
    expect(parseRawLayer(sampleSnapshot())).toBeNull();
    expect(toModel(sampleSnapshot()).raw).toBeUndefined();
  });

  it("makes one pile per non-empty format (never the inbox) and links the pages they feed", () => {
    const raw = parseRawLayer(rawSnapshot());
    expect(raw?.piles.map((p) => p.id)).toEqual(["pile:printed-docs", "pile:emails"]);
    const info = pileOf(raw?.piles[0] as never);
    expect(info).toMatchObject({ format: "printed-docs", count: 10, companions: 2 });
    expect(info?.share).toBeCloseTo(4 / 7);
    expect(raw?.links.filter((l) => l.kind === "pile-page").map((l) => l.target)).toEqual(["2019-fine-grained", "idea-margin"]);
    expect(raw?.links.filter((l) => l.kind === "pile-pile")).toEqual([{ source: "pile:printed-docs", target: "pile:emails", kind: "pile-pile", count: 2 }]);
    expect(isPileId("pile:emails") && formatOfPile("pile:emails")).toBe("emails");
    expect(PILE_PAGE_LINK_CAP).toBe(150);
  });

  it("folds companions out of a page's raw sources", () => {
    const raw = parseRawLayer(rawSnapshot());
    expect(rawSourcesOf(raw ?? undefined, "2019-fine-grained").map((n) => n.path)).toEqual(["raw/printed-docs/a.pdf"]);
  });

  it("draws piles beside the visible pages, tied only to pages that are drawn", () => {
    const model = toModel(rawSnapshot());
    const data = buildGraphData(model, new Set(["idea-margin"]));
    expect(data.nodes.map((n) => n.id).sort()).toEqual(["idea-margin", "pile:emails", "pile:printed-docs"]);
    const kinds = data.links.map((l) => `${l.kind}:${typeof l.target === "string" ? l.target : l.target.id}`);
    expect(kinds).toContain("pile-page:idea-margin");
    expect(kinds).not.toContain("pile-page:2019-fine-grained");
    expect(model.nodes.some((n) => isPileId(n.id))).toBe(false);
  });
});

describe("links", () => {
  it("no link in the graph folder still points at the legacy explorer", () => {
    const here = __dirname;
    const files: string[] = [];
    const walk = (d: string) =>
      readdirSync(d, { withFileTypes: true }).forEach((e) => (e.isDirectory() ? walk(join(d, e.name)) : /\.(ts|tsx)$/.test(e.name) && !/\.test\./.test(e.name) && files.push(join(d, e.name))));
    walk(here);
    const bad = files.filter((f) => /\/explore\b|#\/p\//.test(readFileSync(f, "utf8")));
    expect(bad).toEqual([]);
  });
});
