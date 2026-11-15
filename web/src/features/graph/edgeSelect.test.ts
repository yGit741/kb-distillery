import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { clickEdge, directed, edgeKey, edgeWord, endsOf, lightable, selectable, useEdgeSelect } from "./edgeSelect";
import type { SimLink, SimNode } from "./types";

const link = (source: string, target: string, kind: SimLink["kind"] = "wikilink", extra: Partial<SimLink> = {}): SimLink => ({ source, target, kind, ...extra });
const plain = { shiftKey: false, metaKey: false, ctrlKey: false };
const cmd = { ...plain, metaKey: true };
const shift = { ...plain, shiftKey: true };
const kept = () => [...useEdgeSelect.getState().edges.keys()];
const selected = () => [...useKb.getState().selection].sort();

beforeEach(() => {
  useEdgeSelect.getState().clear();
  useKb.getState().clearSelection();
});

describe("edge identity", () => {
  it("one key per kind and ends, the same for ids and for the node objects force-graph swaps in", () => {
    const n = (id: string) => ({ id }) as SimNode;
    expect(edgeKey(link("a", "b"))).toBe("wikilink|a|b");
    expect(edgeKey({ source: n("a"), target: n("b"), kind: "wikilink" })).toBe("wikilink|a|b");
    expect(edgeKey(link("a", "b", "cites"))).not.toBe(edgeKey(link("a", "b")));
    expect(endsOf({ source: n("x"), target: "y" })).toEqual(["x", "y"]);
  });

  it("pile connectors of the data layer are not edges you select", () => {
    expect(selectable(link("a", "b", "pile-page"))).toBe(false);
    expect(selectable(link("a", "b", "pile-pile"))).toBe(false);
    for (const k of ["wikilink", "related", "book", "shared", "cites"] as const) expect(selectable(link("a", "b", k))).toBe(true);
  });
});

describe("the words on a lit edge", () => {
  it("say what each kind of link means, read from its source to its target", () => {
    expect(edgeWord(link("a", "b", "cites"))).toBe("cites");
    expect(edgeWord(link("a", "b", "wikilink"))).toBe("links to");
    expect(edgeWord(link("a", "b", "book"))).toBe("part of");
    expect(edgeWord(link("a", "b", "related"))).toBe("related to");
    expect(edgeWord(link("a", "b", "shared", { shared: 1 }))).toBe("1 shared source");
    expect(edgeWord(link("a", "b", "shared", { shared: 3 }))).toBe("3 shared sources");
  });

  it("a typed relation drawn as a link says its own kind, in plain words", () => {
    expect(edgeWord(link("a", "b", "related", { rel: "builds_on" }))).toBe("builds on");
    expect(edgeWord(link("a", "b", "related", { rel: "part-of" }))).toBe("part of");
  });

  it("every kind reads one way, with an arrow, except shared sources", () => {
    expect(directed(link("a", "b", "shared"))).toBe(false);
    for (const k of ["wikilink", "related", "book", "cites"] as const) expect(directed(link("a", "b", k))).toBe(true);
  });
});

describe("which edges light up", () => {
  const hidden = new Set(["related"]);
  it("flag edge-select on: every drawn edge of a kind that is shown", () =>
    withFlag("edge-select", true, () => {
      expect(lightable(link("a", "b", "wikilink"), hidden)).toBe(true);
      expect(lightable(link("a", "b", "shared"), hidden)).toBe(true);
      expect(lightable(link("a", "b", "cites"), hidden)).toBe(true);
      expect(lightable(link("a", "b", "related"), hidden)).toBe(false);
      expect(lightable(link("a", "b", "pile-page"), hidden)).toBe(false);
    }));

  it("the canvas may pass the flag it already read, once per pointer move", () => {
    expect(lightable(link("a", "b", "wikilink"), hidden, true)).toBe(true);
    expect(lightable(link("a", "b", "wikilink"), hidden, false)).toBe(false);
  });

  it("flag edge-select off: the citations only, as Citations by meaning had it", () =>
    withFlag("edge-select", false, () => {
      expect(lightable(link("a", "b", "cites"), hidden)).toBe(true);
      expect(lightable(link("a", "b", "wikilink"), hidden)).toBe(false);
      expect(lightable(link("a", "b", "shared"), hidden)).toBe(false);
    }));
});

describe("keeping edges", () => {
  it("a click keeps the edge alone, and its two pages become the selection", () => {
    useKb.getState().setSelection(["z"]);
    clickEdge(link("a", "b"), plain);
    expect(kept()).toEqual(["wikilink|a|b"]);
    expect(selected()).toEqual(["a", "b"]);
    clickEdge(link("c", "d"), plain);
    expect(kept()).toEqual(["wikilink|c|d"]);
    expect(selected()).toEqual(["c", "d"]);
  });

  it("Cmd-, Ctrl- or Shift-click adds an edge with its pages, and takes it out again", () => {
    clickEdge(link("a", "b"), plain);
    clickEdge(link("c", "d"), cmd);
    clickEdge(link("e", "f"), shift);
    clickEdge(link("g", "h"), { ...plain, ctrlKey: true });
    expect(kept()).toHaveLength(4);
    expect(selected()).toEqual(["a", "b", "c", "d", "e", "f", "g", "h"]);
    clickEdge(link("c", "d"), cmd);
    expect(kept()).toEqual(["wikilink|a|b", "wikilink|e|f", "wikilink|g|h"]);
    expect(selected()).toEqual(["a", "b", "e", "f", "g", "h"]);
  });

  it("taking an edge out takes back only the pages it brought, never one picked by itself or shared with a kept edge", () => {
    useKb.getState().setSelection(["a"]);
    clickEdge(link("a", "b"), cmd); // a was picked before: only b is brought
    clickEdge(link("b", "c"), cmd); // b is shared with the first edge
    clickEdge(link("b", "c"), cmd);
    expect(selected()).toEqual(["a", "b"]);
    clickEdge(link("a", "b"), cmd);
    expect(kept()).toEqual([]);
    expect(selected()).toEqual(["a"]);
  });

  it("the page selection leads: clearing it, or picking one page, drops the edges", () => {
    clickEdge(link("a", "b"), plain);
    clickEdge(link("c", "d"), cmd);
    useKb.getState().setSelection(["c", "d", "x"]);
    expect(kept()).toEqual(["wikilink|c|d"]);
    useKb.getState().deselect("d");
    expect(kept()).toEqual([]);
    clickEdge(link("a", "b"), plain);
    useKb.getState().clearSelection();
    expect(kept()).toEqual([]);
    expect(useEdgeSelect.getState().brought.size).toBe(0);
  });

  it("two kinds between the same two pages are two edges", () => {
    clickEdge(link("a", "b", "wikilink"), plain);
    clickEdge(link("a", "b", "shared", { shared: 2 }), cmd);
    expect(kept()).toEqual(["wikilink|a|b", "shared|a|b"]);
    clickEdge(link("a", "b", "wikilink"), cmd);
    expect(kept()).toEqual(["shared|a|b"]);
    expect(selected()).toEqual(["a", "b"]);
  });

  it("the count of drawn kept edges is what the canvas reports, and clearing resets it", () => {
    clickEdge(link("a", "b"), plain);
    useEdgeSelect.getState().setShown(1);
    expect(useEdgeSelect.getState().shown).toBe(1);
    useEdgeSelect.getState().clear();
    expect(useEdgeSelect.getState()).toMatchObject({ shown: 0 });
    expect(kept()).toEqual([]);
  });
});
