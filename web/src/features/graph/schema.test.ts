import { describe, expect, it } from "vitest";
import { defaultTypes, inferLayer, parseSchema, withDataTypes } from "./schema";


describe("types the kit does not define", () => {
  it("guesses a source from the name, anything else is a concept", () => {
    expect(inferLayer("Source")).toBe("source");
    expect(inferLayer("Document")).toBe("source");
    expect(inferLayer("Concept")).toBe("concept");
    expect(inferLayer("Comparison")).toBe("concept");
  });

  it("adds the data's unknown types to the schema once, in their guessed layer", () => {
    const base = parseSchema(undefined);
    const s = withDataTypes(base, ["idea", "Concept", "Source", "Concept"]);
    expect(s.types.length).toBe(base.types.length + 2);
    expect(s.types.find((t) => t.id === "Concept")?.layer).toBe("concept");
    expect(s.types.find((t) => t.id === "Source")?.layer).toBe("source");
    expect(withDataTypes(base, ["idea"])).toBe(base);
  });
});

describe("the types drawn by default", () => {
  const schema = parseSchema({
    types: [
      { id: "topic", label: "Topic", layer: "concept" },
      { id: "company", label: "Company", layer: "concept" },
      { id: "posting", label: "Posting", layer: "source" },
    ],
    default_visible: ["topic"],
  });
  it("are the kit's defaults when the kb has a page of one of them, or no page yet", () => {
    expect([...defaultTypes(schema, [{ type: "topic" }, { type: "company" }])]).toEqual(["topic"]);
    expect([...defaultTypes(schema, [])]).toEqual(["topic"]);
  });
  it("are the whole concept layer when no page is of a default type, so the graph is never empty", () => {
    expect([...defaultTypes(schema, [{ type: "company" }, { type: "posting" }])].sort()).toEqual(["company", "topic"]);
  });
});
