import { FOCUS } from "./model";
import { print } from "./grammar";
import { fromSentence } from "./sentence";

describe("neighbours in a sentence", () => {
  it("'neighbors of this' and 'expand this' are one hop around the focus", () => {
    for (const t of ["neighbors of this", "neighbours of this", "expand this", "show the neighbors of this page"]) {
      const r = fromSentence(t);
      expect(r.unknown).toBeUndefined();
      expect(r.layers).toHaveLength(1);
      expect(r.layers[0]!.subgraph.nodes).toEqual([{ t: "hops", of: FOCUS, n: 1 }]);
      expect(r.lines).toEqual(["show nodes within 1 hop of this"]);
      expect(print(r.layers[0]!)).toBe(r.lines[0]);
    }
  });

  it("a named page reads the same way", () => {
    expect(fromSentence('neighbors of "Kernel methods"').lines).toEqual(['show nodes within 1 hop of "Kernel methods"']);
  });
});
