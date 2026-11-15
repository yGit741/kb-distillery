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
    expect(fromSentence("colour by kind").lines).toEqual(["style nodes color by format"]);
    expect(fromSentence("size by links").lines).toEqual(["style nodes size by connections"]);
    expect(fromSentence("thin mentions edges").lines).toEqual(["style edges width by thin for type mentions"]);
    expect(fromSentence("Hide orphans.").lines).toEqual(["hide nodes degree = 0"]);
  });

  it("reads the ways people say hide", () => {
    for (const t of ["exclude all orphans", "Exclude orphans", "remove orphans", "drop orphans", "filter out orphans", "without orphans", "no orphans"])
      expect(fromSentence(t).lines, t).toEqual(["hide nodes degree = 0"]);
    for (const t of ["don't show orphans", "dont show orphans", "don’t show orphans", "do not show orphans", "never show orphans"])
      expect(fromSentence(t).lines, t).toEqual(["hide nodes degree = 0"]);
    expect(fromSentence("no leaves").lines).toEqual(["hide nodes degree = 1"]);
    expect(fromSentence("without favorites").lines).toEqual(["hide nodes favorite"]);
    // "no <type> notes" keeps its own meaning
    expect(fromSentence("no question notes").unknown).toBeUndefined();
    expect(fromSentence("no question notes").lines[0]).toMatch(/^show nodes not /);
    expect(fromSentence("papers with more than 5 links").lines).toEqual(["show nodes type paper and degree > 5"]);
    expect(fromSentence("exclude papers with more than 5 links").lines).toEqual(["hide nodes type paper and degree > 5"]);
  });

  it("reads a line without commas, the legend's names and small typos (your line)", () => {
    expect(fromSentence("only orphans color by theams").lines).toEqual(["show nodes degree = 0", "style nodes color by area"]);
    expect(fromSentence("only orphans colour by theme").lines).toEqual(["show nodes degree = 0", "style nodes color by area"]);
    expect(fromSentence("orphnas").lines).toEqual(["show nodes degree = 0"]);
    expect(fromSentence("dont show orphans and colour by maturity").lines).toEqual(["hide nodes degree = 0", "style nodes color by status"]);
    expect(fromSentence("only papers and hide people").lines).toEqual(["show nodes type paper", "hide nodes type person"]);
    expect(fromSentence("colour by digest status").lines).toEqual(["style nodes color by depth"]);
    expect(fromSentence("colour by date added").lines).toEqual(["style nodes color by added"]);
    expect(fromSentence("colour by source count").lines).toEqual(["style nodes color by evidence"]);
    expect(fromSentence("colur by type").lines).toEqual(["style nodes color by format"]);
  });

  it("never mends a page name, and a colour it cannot place is left for the model", () => {
    expect(fromSentence("within 2 hops of Colors of noise").lines[0]).toContain("Colors of noise");
    expect(fromSentence('about "Colorado"').lines[0]).toContain("Colorado");
    expect(fromSentence("don't show orphnas").lines).toEqual(["hide nodes degree = 0"]);
    expect(fromSentence("favorites").lines).toEqual(["show nodes favorite"]);
    expect(fromSentence("colour by score").lines).toEqual(["style nodes color by score"]);
    // topic colouring is a view of its own, never a layer colour
    expect(fromSentence("colour by topic").unknown).toBe("colour by topic");
    expect(fromSentence("colour by year").unknown).toBe("colour by year");
    expect(fromSentence("colour by vibes").unknown).toBe("colour by vibes");
  });

  it("returns unknown for text it cannot read", () => {
    for (const t of ["make it feel calmer", "", "sparkles", "show me the best ideas about love", "colour"]) {
      const r = fromSentence(t);
      expect(r.layers).toEqual([]);
      expect(r.unknown).toBe(t.trim());
    }
  });
});
