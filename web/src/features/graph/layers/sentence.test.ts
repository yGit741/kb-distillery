import { fromSentence } from "./sentence";
import { SENTENCES } from "./sentence.fixtures";

describe("fromSentence", () => {
  it.each(SENTENCES.map((s) => [s.text, s.lines] as const))("%s", (text, lines) => {
    const r = fromSentence(text, "replace");
    expect(r.unknown).toBeUndefined();
    expect(r.lines).toEqual(lines);
    expect(r.layers).toHaveLength(lines.length);
  });

  it("reads the synonyms", () => {
    expect(fromSentence("only orphans").lines).toEqual(["show nodes degree = 0"]);
    expect(fromSentence("colour by kind").lines).toEqual(["style nodes color by type"]);
    expect(fromSentence("size by links").lines).toEqual(["style nodes size by connections"]);
    expect(fromSentence("thin mentions edges").lines).toEqual(["style edges width by thin for type mentions"]);
    expect(fromSentence("Hide orphans.").lines).toEqual(["hide nodes degree = 0"]);
  });

  it("reads the ways people say hide", () => {
    for (const t of ["exclude all orphans", "Exclude orphans", "remove orphans", "drop orphans", "filter out orphans", "without orphans", "no orphans"])
      expect(fromSentence(t).lines, t).toEqual(["hide nodes degree = 0"]);
    expect(fromSentence("no leaves").lines).toEqual(["hide nodes degree = 1"]);
    expect(fromSentence("without favorites").lines).toEqual(["hide nodes favorite"]);
    // "no <type> notes" keeps its own meaning
    expect(fromSentence("no question notes").unknown).toBeUndefined();
    expect(fromSentence("no question notes").lines[0]).toMatch(/^show nodes not /);
    expect(fromSentence("papers with more than 5 links").lines).toEqual(["show nodes type paper and degree > 5"]);
    expect(fromSentence("exclude papers with more than 5 links").lines).toEqual(["hide nodes type paper and degree > 5"]);
  });

  it("returns unknown for text it cannot read", () => {
    for (const t of ["make it feel calmer", "", "sparkles", "show me the best ideas about love", "colour"]) {
      const r = fromSentence(t);
      expect(r.layers).toEqual([]);
      expect(r.unknown).toBe(t.trim());
    }
  });
});
