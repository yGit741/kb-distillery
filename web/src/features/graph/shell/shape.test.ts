import type { StyleSpec } from "@/api";
import { sampleNodes } from "../fixtures";
import { dropTypes, pillText, planStyle, shapeIds, typesOfLabel } from "./shape";
import { makeView } from "../pageSearch";

const style = (over: Partial<StyleSpec> = {}): StyleSpec => ({ hide_edge_kinds: [], hide_labels: [], ...over });
const nodes = sampleNodes;
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));

describe("planStyle", () => {
  it("maps the clauses the graph has onto its knobs", () => {
    const p = planStyle(style({ colour_by: { by: "prop", name: "depth" }, size_by: { by: "degree" }, layout: "radial" }), nodes);
    expect(p.patch).toEqual({ colorBy: "depth", sizeBy: "connections", layoutMode: "anchored" });
    expect(p.skipped).toEqual([]);
    expect(planStyle(style({ colour_by: { by: "degree" } }), nodes).patch.colorBy).toBe("degree");
    expect(planStyle(style({ colour_by: { by: "prop", name: "maturity" } }), nodes).patch.colorBy).toBe("status");
    expect(planStyle(style({ layout: "force" }), nodes).patch.layoutMode).toBe("free");
  });

  it("group by area gathers the pages by theme (and wins over an explicit force layout)", () => {
    expect(planStyle(style({ group_by: { by: "prop", name: "areas" }, layout: "force" }), nodes).patch.layoutMode).toBe("anchored");
  });

  it("lists what it cannot draw, with the reason, and changes nothing for it", () => {
    const p = planStyle(
      style({
        colour_by: { by: "prop", name: "type" },
        size_by: { by: "prop", name: "year" },
        group_by: { by: "prop", name: "year" },
        layout: "timeline",
        label: "slug",
        hide_edge_kinds: ["COLLABORATES_WITH"],
        hide_labels: ["Nonsense"],
      }),
      nodes,
    );
    expect(p.patch).toEqual({});
    expect(p.skipped).toHaveLength(7);
    expect(p.skipped[0]).toMatch(/timeline/);
    expect(p.skipped.join("|")).toMatch(/colour by type \(the mark already shows the type\)/);
  });

  it("hide MENTIONS hides the link kinds the canvas draws for it", () => {
    expect(planStyle(style({ hide_edge_kinds: ["MENTIONS", "SHARES_SOURCE"] }), nodes).hideLinkKinds).toEqual(["wikilink", "related", "shared"]);
  });

  it("hide takes a node label or a layer, from the types this graph has", () => {
    const kit = [...sampleNodes, { type: "ai-chat", layer: "source" }, { type: "company", layer: "entity" }];
    expect(typesOfLabel("Paper", kit)).toEqual(["paper"]);
    expect(typesOfLabel("AiChat", kit)).toEqual(["ai-chat"]);
    expect(typesOfLabel("Company", kit)).toEqual(["company"]);
    expect(typesOfLabel("Source", kit).sort()).toEqual(["ai-chat", "paper"]);
    expect(typesOfLabel("Nope", kit)).toEqual([]);
    expect(planStyle(style({ hide_labels: ["Person", "Question"] }), nodes).hideTypes).toEqual(["person", "question"]);
  });
});

describe("rows and pills", () => {
  it("shapeIds takes every cell that is a page, once, in row order", () => {
    const res = { rows: [["idea-margin", "Margin", 3], [["jane-doe", "idea-margin"]], ["nothing"]] };
    expect(shapeIds(res, byId)).toEqual(["idea-margin", "jane-doe"]);
  });

  it("dropTypes takes a type out of a view's hits and its neighbours", () => {
    const view = makeView("picked", "x", ["idea-margin", "jane-doe"], byId, new Map([["idea-margin", ["q-why-big-nets-work"]]]))!;
    const next = dropTypes(view, new Set(["person", "question"]), byId)!;
    expect([...next.hits]).toEqual(["idea-margin"]);
    expect([...next.shown]).toEqual(["idea-margin"]);
    expect(dropTypes(view, new Set(["idea", "person"]), byId)).toBeNull();
  });

  it("pillText: the canonical style then the pages", () => {
    expect(pillText("colour by areas;size by degree", 1)).toBe("colour by areas; size by degree · 1 page");
    expect(pillText("", 5)).toBe("5 pages");
    expect(pillText("layout force", null)).toBe("layout force");
  });
});
