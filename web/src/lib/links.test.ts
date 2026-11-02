import { PAGE_LINK, WIKILINK, link, plain, targets, toDisk, toLlm } from "./links";

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

  it("reads page links and wikilinks in order, not images, urls or paths", () => {
    const t = "[A](a.md) ![i](i.md) [w](https://x.org/w.md) [p](wiki/p.md) [[b]] [C](c.md#h) [esc \\[x\\]](d.md)";
    expect(targets(t)).toEqual(["a", "b", "c", "d"]);
  });

  it("matches page links with label, slug and anchor", () => {
    const got = Array.from("[A](a.md) [B](b.md#why) [esc \\[x\\]](c.md)".matchAll(PAGE_LINK), (m) => [m[1], m[2], m[3]]);
    expect(got).toEqual([["A", "a", undefined], ["B", "b", "why"], ["esc \\[x\\]", "c", undefined]]);
  });

  it("builds links like core.links.link", () => {
    expect(link("a", "Tensor rank")).toBe("[Tensor rank](a.md)");
    expect(link("a")).toBe("[a](a.md)");
    expect(link("a", "Why [x]", "Why it works")).toBe("[Why \\[x\\]](a.md#why-it-works)");
  });

  it("plain reduces both forms to their text", () => {
    expect(plain("see [A \\[1\\]](a.md) and [[b|B]] and [[c]]")).toBe("see A [1] and B and c");
  });

  it("toLlm and toDisk are the identity for now", () => {
    expect(toLlm("[[a]]")).toBe("[[a]]");
    expect(toDisk("[[a]]")).toBe("[[a]]");
  });
});
