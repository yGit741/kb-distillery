import { describe, expect, it } from "vitest";
import { inferLayer, parseSchema, withDataTypes } from "./schema";


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
