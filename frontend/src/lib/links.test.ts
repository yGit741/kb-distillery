import { WIKILINK, targets, toDisk, toLlm } from "./links";

describe("links", () => {
  it("lists targets in order, stripped, duplicates kept", () => {
    const t = "a [[one]] b [[ two |Label]] c [[three#Head]] d [[one]] e [[four\\|alias]]";
    expect(targets(t)).toEqual(["one", "two", "three", "one", "four"]);
  });

  it("is repeatable and tolerates empty input", () => {
    expect(targets("[[x]]")).toEqual(["x"]);
    expect(targets("[[x]]")).toEqual(["x"]);
    expect(targets("")).toEqual([]);
    expect(targets(undefined as unknown as string)).toEqual([]);
  });

  it("matches whole links with slug and label, dropping the heading", () => {
    const got = Array.from("[[a#h|L]] [[b]] [[c\\|M]]".matchAll(WIKILINK), (m) => [m[1], m[2]]);
    expect(got).toEqual([["a", "L"], ["b", undefined], ["c", "M"]]);
  });

  it("replaces like the old inline copy", () => {
    expect("see [[a|Alpha]] and [[b]]".replace(WIKILINK, (_m, s: string, l?: string) => (l || s).trim()))
      .toBe("see Alpha and b");
  });

  it("toLlm and toDisk are the identity for now", () => {
    expect(toLlm("[[a]]")).toBe("[[a]]");
    expect(toDisk("[[a]]")).toBe("[[a]]");
  });
});
