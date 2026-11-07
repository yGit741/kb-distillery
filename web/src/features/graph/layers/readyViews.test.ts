import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { isParseError, parse, print } from "./grammar";
import { readyCard, specLayers } from "./readyViews";
import { makeLayer } from "./model";

// the fixture is the kits themselves: every view of every kit under src/kb_distillery/kits
const KITS = join(__dirname, "../../../../../src/kb_distillery/kits");

interface KitView {
  kit: string;
  id: string;
  lines: string[];
}

function kitViews(): KitView[] {
  const out: KitView[] = [];
  for (const kit of readdirSync(KITS, { withFileTypes: true }).filter((d) => d.isDirectory())) {
    let files: string[] = [];
    try {
      files = readdirSync(join(KITS, kit.name, "views")).filter((f) => f.endsWith(".toml"));
    } catch {
      continue;
    }
    for (const f of files) {
      const text = readFileSync(join(KITS, kit.name, "views", f), "utf8");
      const blocks = text.split(/^\[\[view\]\]\s*$/m).slice(1);
      for (const b of blocks) {
        const id = /^id = "([^"]+)"/m.exec(b)?.[1] ?? "";
        const layers = /^layers = (\[.*\])\s*$/m.exec(b)?.[1] ?? "[]";
        out.push({ kit: kit.name, id, lines: JSON.parse(layers) as string[] });
      }
    }
  }
  return out;
}

describe("the kits' ready views", () => {
  const all = kitViews();

  it("finds the base and research views", () => {
    const ids = (kit: string) => all.filter((v) => v.kit === kit).map((v) => v.id);
    expect(ids("base")).toEqual(expect.arrayContaining(["contradictions", "orphans", "hubs", "by-type", "recent-additions", "gaps", "open-contradictions", "frontier", "quiet-hubs", "neighborhood"]));
    expect(ids("research").length).toBeGreaterThanOrEqual(2);
  });

  it("every layer line of every view parses with the grammar and prints back the same", () => {
    for (const v of all) {
      expect(v.lines.length, `${v.kit}/${v.id}`).toBeGreaterThan(0);
      for (const line of v.lines) {
        const layer = parse(line);
        expect(isParseError(layer), `${v.kit}/${v.id}: ${line}`).toBe(false);
        if (!isParseError(layer)) expect(print(layer)).toBe(line);
      }
    }
  });
});

describe("readyCard", () => {
  it("parses every line into a layer", () => {
    const c = readyCard({ id: "x", name: "X", description: "d", layers: ["show nodes degree = 0", "style nodes color by type"] });
    expect(c.layers?.map((l) => l.kind)).toEqual(["show", "style"]);
  });

  it("a line it cannot read makes the view unavailable instead of throwing", () => {
    const c = readyCard({ id: "x", name: "X", description: "d", layers: ["show nodes degree = 0", "make it pretty"] });
    expect(c.layers).toBeNull();
    expect(c.error).toContain("make it pretty");
  });
});

describe("specLayers", () => {
  it("reads a v2 spec's layers with fresh ids, and nothing else", () => {
    const l = makeLayer("show", "nodes", {}, "All");
    const got = specLayers({ v: 2, layers: [l], text: "All" });
    expect(got).toHaveLength(1);
    expect(got![0]!.id).not.toBe(l.id);
    expect(specLayers({ v: 1, story: "map" })).toBeNull();
    expect(specLayers({ v: 2, layers: [] })).toBeNull();
    expect(specLayers({ v: 2, layers: [{ nope: true }] })).toBeNull();
  });
});
