import { sampleNodes, node } from "./fixtures";
import { computeVisible, matchRule, passesText, type Rule, type VisibilityOptions } from "./rules";

const rule = (o: Partial<Rule>): Rule => ({ mode: "include", field: "type", op: "is", value: "", ...o });
const opts = (o: Partial<VisibilityOptions> = {}): VisibilityOptions => ({
  shownTypes: null,
  shownDepths: null,
  search: "",
  rules: [],
  restrict: null,
  force: false,
  revealed: new Set(),
  ...o,
});

describe("matchRule", () => {
  const n = node("2019-fine-grained", { type: "paper", layer: "source", depth: "full", year: 2019, inDegree: 4, areas: ["learning-theory", "info-theory"] });
  it("compares is / is-not case-insensitively", () => {
    expect(matchRule(n, rule({ value: "Paper" }))).toBe(true);
    expect(matchRule(n, rule({ op: "is-not", value: "paper" }))).toBe(false);
  });
  it("searches the joined areas and the slug/title", () => {
    expect(matchRule(n, rule({ field: "area", op: "contains", value: "info" }))).toBe(true);
    expect(matchRule(n, rule({ field: "slug", op: "not-contains", value: "fine" }))).toBe(false);
    expect(matchRule(n, rule({ field: "title", op: "contains", value: "fine grained" }))).toBe(true);
  });
  it("compares numbers with gte / lte, and an empty numeric value counts as 0", () => {
    expect(matchRule(n, rule({ field: "inDegree", op: "gte", value: "4" }))).toBe(true);
    expect(matchRule(n, rule({ field: "inDegree", op: "gte", value: "5" }))).toBe(false);
    expect(matchRule(n, rule({ field: "year", op: "lte", value: "2018" }))).toBe(false);
    expect(matchRule(n, rule({ field: "outDegree", op: "gte", value: "" }))).toBe(true);
  });
  it("an empty text value matches everything; exclude inverts a real match", () => {
    expect(matchRule(n, rule({ value: "" }))).toBe(true);
    expect(matchRule(n, rule({ mode: "exclude", value: "paper" }))).toBe(false);
    expect(matchRule(n, rule({ mode: "exclude", field: "depth", value: "deep" }))).toBe(true);
  });
  it("filters on the layer and depth of the new model", () => {
    expect(matchRule(n, rule({ field: "layer", value: "source" }))).toBe(true);
    expect(matchRule(n, rule({ field: "depth", value: "easy" }))).toBe(false);
  });
});

describe("passesText", () => {
  it("matches slug or title", () => {
    expect(passesText(node("a-b", { title: "Margin Bounds" }), "margin")).toBe(true);
    expect(passesText(node("a-b", { title: "Margin Bounds" }), "a-b")).toBe(true);
    expect(passesText(node("a-b", { title: "Margin Bounds" }), "zzz")).toBe(false);
  });
});

describe("computeVisible", () => {
  const ids = (s: Set<string>) => [...s].sort();
  it("draws only the shown types (people off by default)", () => {
    const v = computeVisible(sampleNodes, opts({ shownTypes: new Set(["topic", "idea", "question"]) }));
    expect(ids(v)).toEqual(["idea-margin", "q-why-big-nets-work", "topic-learning-theory"]);
  });
  it("null shows every type", () => {
    expect(computeVisible(sampleNodes, opts()).size).toBe(sampleNodes.length);
  });
  it("hides source depths that are switched off, but not other layers", () => {
    const v = computeVisible(sampleNodes, opts({ shownDepths: new Set(["full", "deep"]) }));
    expect(v.has("2020-listed-paper")).toBe(false);
    expect(v.has("2019-fine-grained")).toBe(true);
    expect(v.has("topic-learning-theory")).toBe(true);
  });
  it("combines text and rules", () => {
    const v = computeVisible(sampleNodes, opts({ search: "learning", rules: [rule({ field: "type", value: "topic" })] }));
    expect(ids(v)).toEqual(["topic-learning-theory"]);
  });
  it("a view restricts the drawing; forced, it draws its pages past every filter", () => {
    const only = new Set(["2020-listed-paper", "idea-margin"]);
    const shown = new Set(["idea"]);
    expect(ids(computeVisible(sampleNodes, opts({ shownTypes: shown, restrict: only })))).toEqual(["idea-margin"]);
    expect(ids(computeVisible(sampleNodes, opts({ shownTypes: shown, restrict: only, force: true })))).toEqual(["2020-listed-paper", "idea-margin"]);
  });
  it("revealed sources are drawn whatever the type filter says, and unknown ids are ignored", () => {
    const v = computeVisible(sampleNodes, opts({ shownTypes: new Set(["topic"]), revealed: new Set(["2019-fine-grained", "ghost"]) }));
    expect(v.has("2019-fine-grained")).toBe(true);
    expect(v.has("ghost")).toBe(false);
  });
});
