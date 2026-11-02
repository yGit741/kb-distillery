import { sampleNodes } from "./fixtures";
import { colorKeyRows, depthRows, layerGroups } from "./legendModel";
import { parseSchema, presentTypes } from "./schema";
import { sampleSnapshot } from "./fixtures";

const schema = parseSchema(sampleSnapshot().schema);

describe("schema", () => {
  it("reads types, layers and the default view from /api/graph", () => {
    expect(schema.defaultVisible).toEqual(["topic", "idea", "question"]);
    expect(schema.types.find((t) => t.id === "course")?.layer).toBe("collection");
  });
  it("falls back to the data model when the payload is missing", () => {
    const s = parseSchema(undefined);
    expect(s.types.map((t) => t.id)).toContain("blog-post");
    expect(s.defaultVisible).toEqual(["topic", "idea", "question"]);
  });
  it("lists present types in schema order, then unknown ones", () => {
    expect(presentTypes(schema, ["idea", "paper", "weird"]).map((t) => t.id)).toEqual(["paper", "idea", "weird"]);
  });
});

describe("layerGroups", () => {
  const visible = new Set(["idea-margin", "topic-learning-theory", "q-why-big-nets-work"]);
  const groups = layerGroups(sampleNodes, visible, schema, new Set(["topic", "idea", "question"]));
  it("groups types by layer with counts and a tri-state", () => {
    expect(groups.map((g) => g.layer)).toEqual(["source", "collection", "concept"]);
    const concept = groups.find((g) => g.layer === "concept");
    expect(concept?.state).toBe("some"); // person is off
    expect(concept?.rows.find((r) => r.id === "person")).toMatchObject({ total: 1, visible: 0, shown: false });
    expect(groups.find((g) => g.layer === "source")?.state).toBe("none");
  });
  it("null means every type is on", () => {
    expect(layerGroups(sampleNodes, visible, schema, null).every((g) => g.state === "all")).toBe(true);
  });
});

describe("depthRows / colorKeyRows", () => {
  it("counts sources per depth from listed to deep", () => {
    expect(depthRows(sampleNodes, new Set(["full"])).map((d) => [d.depth, d.total, d.shown])).toEqual([
      ["listed", 1, false],
      ["easy", 0, false],
      ["full", 1, true],
      ["deep", 0, false],
    ]);
  });
  it("builds the colour key from what is drawn, most common first", () => {
    const rows = colorKeyRows(sampleNodes, new Set(sampleNodes.map((n) => n.id)), "status");
    expect(rows[0]).toMatchObject({ label: "growing", count: 2 });
    expect(colorKeyRows(sampleNodes, new Set(), "status")).toEqual([]);
  });
});
