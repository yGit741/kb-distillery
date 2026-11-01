import { HEADLINE_STORIES, STORIES } from "../lab/views";
import { EXPLAIN, explainOf, explained, storyName } from "./explain";

describe("view explanations", () => {
  it("every headline view is explained, with at least one algorithm and two questions", () => {
    expect(HEADLINE_STORIES.length).toBeGreaterThanOrEqual(3);
    for (const s of HEADLINE_STORIES) {
      const e = explainOf(s.id);
      expect(e, s.id).toBeDefined();
      expect(e?.filters.length, s.id).toBeGreaterThan(20);
      expect(e?.layout.length, s.id).toBeGreaterThan(20);
      expect(e?.ranking.length, s.id).toBeGreaterThan(20);
      expect(e?.algorithms.length, s.id).toBeGreaterThanOrEqual(1);
      expect(s.headline?.questions.length, s.id).toBeGreaterThanOrEqual(2);
      expect(explained(s)).toBe(true);
    }
  });

  it("explanations only exist for real stories", () => {
    const ids = new Set(STORIES.map((s) => s.id));
    for (const k of Object.keys(EXPLAIN)) expect(ids.has(k), k).toBe(true);
    expect(explainOf("nope")).toBeUndefined();
  });

  it("names a view by its pill label, then its name, then the id", () => {
    expect(storyName("map")).toBe("Map");
    expect(storyName("questions")).toBe("Open questions first");
    expect(storyName("zzz")).toBe("zzz");
  });
});
