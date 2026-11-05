import { storyById, storyTypes } from "./views";

const research = { types: [{ id: "topic", layer: "concept" as const }, { id: "idea", layer: "concept" as const }, { id: "paper", layer: "source" as const }, { id: "book", layer: "collection" as const }] };
const jobs = { types: [{ id: "company", layer: "concept" as const }, { id: "role", layer: "concept" as const }, { id: "person", layer: "concept" as const }, { id: "notes", layer: "source" as const }, { id: "series", layer: "collection" as const }] };

describe("storyTypes", () => {
  it("Map draws the concept and source layers of whatever kit the kb uses, never the collection hubs", () => {
    const map = storyById("map");
    expect(map?.layers).toEqual(["concept", "source"]);
    expect([...storyTypes(map, research)!].sort()).toEqual(["idea", "paper", "topic"]);
    expect([...storyTypes(map, jobs)!].sort()).toEqual(["company", "notes", "person", "role"]);
  });

  it("a view with its own type list keeps it; no view leaves the schema default", () => {
    expect([...storyTypes({ types: ["topic"] }, jobs)!]).toEqual(["topic"]);
    expect(storyTypes(undefined, jobs)).toBeNull();
    expect(storyTypes({}, jobs)).toBeNull();
  });
});
