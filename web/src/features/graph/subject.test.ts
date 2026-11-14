import { buildNeighborMap } from "./graphData";
import { parseSchema } from "./schema";
import { DEFAULT_PREFS, useGraphUi } from "./store";
import { withFlag } from "@/flags/testing";
import { applySubject, colourFor, settledColour, sideOffset, sourceCounts, subjectOf, subjectWord, typesFor } from "./subject";
import { node } from "./fixtures";

const schema = parseSchema({
  types: [
    { id: "topic", label: "Topic", layer: "concept" },
    { id: "idea", label: "Idea", layer: "concept" },
    { id: "book", label: "Book", layer: "collection" },
    { id: "paper", label: "Paper", layer: "source" },
    { id: "lecture", label: "Lecture", layer: "source" },
  ],
  default_visible: ["topic", "idea"],
});

describe("which view the graph is in", () => {
  it("is Concepts until a source type is drawn; every type drawn is Sources", () => {
    expect(subjectOf(schema, new Set(["topic", "idea"]))).toBe("concepts");
    expect(subjectOf(schema, new Set(["topic", "book"]))).toBe("concepts");
    expect(subjectOf(schema, new Set(["topic", "paper"]))).toBe("sources");
    expect(subjectOf(schema, null)).toBe("sources");
  });
});

describe("the types a view draws", () => {
  it("Concepts keeps the concept types on screen and drops sources and collections", () => {
    expect([...typesFor("concepts", schema, new Set(["idea", "book", "paper"]))]).toEqual(["idea"]);
  });
  it("Sources keeps those concept types and adds every source type", () => {
    expect([...typesFor("sources", schema, new Set(["idea"]))]).toEqual(["idea", "paper", "lecture"]);
  });
  it("with no concept type on screen a view draws the whole concept layer, never nothing", () => {
    expect([...typesFor("concepts", schema, new Set(["paper"]))]).toEqual(["topic", "idea"]);
    expect([...typesFor("sources", schema, null)]).toEqual(["topic", "idea", "paper", "lecture"]);
  });
});

describe("switching the view", () => {
  beforeEach(() => useGraphUi.setState({ ...DEFAULT_PREFS, shownTypes: undefined, hiddenKeys: new Set(["x"]) }));

  it("draws the view's types, moves to a colouring the view offers and clears hidden colour values", () => {
    expect(applySubject("sources", schema, new Set(["topic", "idea"]))).toBe(true);
    const s = useGraphUi.getState();
    expect([...s.shownTypes!]).toEqual(["topic", "idea", "paper", "lecture"]);
    expect(s.colorBy).toBe("format");
    expect(s.hiddenKeys.size).toBe(0);
    expect(applySubject("concepts", schema, s.shownTypes!)).toBe(true);
    expect([...useGraphUi.getState().shownTypes!]).toEqual(["topic", "idea"]);
    expect(useGraphUi.getState().colorBy).toBe("format"); // both views offer it
  });

  it("does nothing when the view is already on", () => {
    expect(applySubject("concepts", schema, new Set(["topic"]))).toBe(false);
    expect(useGraphUi.getState().hiddenKeys.size).toBe(1);
  });

  it("a colouring the other view does not offer falls back to that view's first", () => {
    expect(colourFor("sources", "area")).toBe("format");
    expect(colourFor("concepts", "depth")).toBe("area");
    expect(colourFor("concepts", "status")).toBe("status");
  });
});

describe("the source count of a concept", () => {
  it("counts distinct source pages linked either way, over the whole kb; a concept with none has no count", () => {
    const nodes = [node("a", { layer: "concept", type: "idea" }), node("b", { layer: "concept", type: "idea" }), node("p1", { layer: "source", type: "paper" }), node("p2", { layer: "source", type: "paper" })];
    const links = [
      { source: "a", target: "p1" },
      { source: "p1", target: "a" },
      { source: "p2", target: "a" },
      { source: "a", target: "b" },
    ];
    const counts = sourceCounts(nodes, buildNeighborMap(links));
    expect(counts.get("a")).toBe(2);
    expect(counts.has("b")).toBe(false);
    expect(counts.has("p1")).toBe(false);
  });
});

describe("the > line's view words", () => {
  it("reads concepts and sources, with or without the word view, and nothing else", () => {
    expect(subjectWord(" Concepts ")).toBe("concepts");
    expect(subjectWord("sources view")).toBe("sources");
    expect(subjectWord("show sources")).toBeNull();
    expect(subjectWord("colour by area")).toBeNull();
  });
});

describe("the two sides of the Sources view", () => {
  it("sit further apart as more pages are drawn", () => {
    expect(sideOffset(70, 25)).toBe(Math.max(220, 70 * (2 + 5 / 4)));
    expect(sideOffset(70, 900)).toBeGreaterThan(sideOffset(70, 25));
  });
});

describe("the Health view (flag knowledge-health)", () => {
  beforeEach(() => useGraphUi.setState({ ...DEFAULT_PREFS, shownTypes: undefined, hiddenKeys: new Set() }));

  it("is the concepts alone coloured by source support; a drawn source type is still Sources", () => {
    expect(subjectOf(schema, new Set(["topic", "idea"]), "support")).toBe("health");
    expect(subjectOf(schema, new Set(["topic", "idea"]), "area")).toBe("concepts");
    expect(subjectOf(schema, new Set(["topic", "paper"]), "support")).toBe("sources");
  });

  it("switching to it keeps the concept types and takes its one colouring; switching back leaves that colouring", () => {
    expect(applySubject("health", schema, new Set(["idea", "paper"]))).toBe(true);
    expect([...useGraphUi.getState().shownTypes!]).toEqual(["idea"]);
    expect(useGraphUi.getState().colorBy).toBe("support");
    expect(applySubject("health", schema, useGraphUi.getState().shownTypes!)).toBe(false);
    expect(applySubject("concepts", schema, useGraphUi.getState().shownTypes!)).toBe(true);
    expect(useGraphUi.getState().colorBy).toBe("area");
  });

  it("is reached by its view word, known only with the flag", () => {
    expect(subjectWord("health")).toBeNull();
    expect(subjectWord("Health view", true)).toBe("health");
    expect(subjectWord("sources", true)).toBe("sources");
  });

  it("the support colouring restored outside Health falls back to the view's own first colouring", () => {
    const concepts = new Set(["topic", "idea"]);
    expect(settledColour("support", true, schema, concepts)).toBeNull(); // Health itself
    expect(settledColour("area", false, schema, concepts)).toBeNull(); // any other colouring is left alone
    expect(settledColour("support", false, schema, concepts)).toBe("area"); // the flag off
    expect(settledColour("support", true, schema, new Set(["topic", "paper"]))).toBe("format"); // sources drawn
  });

  it("knowledge-health off: a restored support colouring does not make the view read as Health", () =>
    withFlag("knowledge-health", false, () => {
      useGraphUi.setState({ colorBy: "support" });
      expect(applySubject("concepts", schema, new Set(["topic", "idea"]))).toBe(false); // already Concepts
      expect(useGraphUi.getState().colorBy).toBe("support"); // untouched here; the screen settles it
    }));

  it("knowledge-health on: Concepts leaves Health and its colouring", () =>
    withFlag("graph-intent", true, () =>
      withFlag("knowledge-health", true, () => {
        useGraphUi.setState({ colorBy: "support" });
        expect(applySubject("concepts", schema, new Set(["topic", "idea"]))).toBe(true);
        expect(useGraphUi.getState().colorBy).toBe("area");
      })));
});
