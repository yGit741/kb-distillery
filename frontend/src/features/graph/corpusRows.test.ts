import { describe, expect, it } from "vitest";
import type { CorpusRow } from "@/api";
import { dispositionChips, filterRows, fromCorpus, nameOfPath, parentOf, sortRows } from "./corpusRows";

const r = (path: string, over: Partial<CorpusRow> = {}): CorpusRow => ({ path, sha1: "", title: "", digestion: "", collection: [], disposition: "queued", ...over });
const rows: CorpusRow[] = [
  r("raw/web-clips/post.md", { slug: "article-post", disposition: "source", year: 2024 }),
  r("raw/web-clips/post-01.png", { disposition: "asset:raw/web-clips/post.md" }),
  r("raw/web-clips/post-02.png", { disposition: "asset:raw/web-clips/post.md" }),
  r("raw/web-clips/other.md"),
  r("raw/web-clips/old.md", { disposition: "dupe:raw/web-clips/other.md" }),
  r("raw/web-clips/note.md", { disposition: "skip", collection: ["series-x"] }),
  r("raw/web-clips/parsed.md", { disposition: "sidecar" }),
];

describe("corpus drawer rows", () => {
  it("folds asset / ink / dupe / sidecar rows into their parent", () => {
    const list = fromCorpus(rows, "web-clips");
    expect(list.map((x) => x.path)).toEqual(["raw/web-clips/post.md", "raw/web-clips/other.md", "raw/web-clips/note.md"]);
    expect(list.map((x) => x.companions)).toEqual([2, 1, 0]);
  });

  it("reads the parent from companion_of or the disposition tail", () => {
    expect(parentOf({ disposition: "ink:raw/handwritten/a.pdf" })).toBe("raw/handwritten/a.pdf");
    expect(parentOf({ disposition: "queued", companion_of: "raw/x" })).toBe("raw/x");
    expect(parentOf({ disposition: "source" })).toBeNull();
  });

  it("counts states, filters by chip and text, sorts with blanks last", () => {
    const list = fromCorpus(rows, "web-clips");
    expect(dispositionChips(list)).toEqual([{ id: "queued", n: 1 }, { id: "skip", n: 1 }, { id: "source", n: 1 }]);
    expect(filterRows(list, "", new Set(["skip"])).map((x) => nameOfPath(x.path))).toEqual(["note.md"]);
    expect(filterRows(list, "series-x", new Set()).length).toBe(1);
    expect(sortRows(list, "year", -1).map((x) => x.year)).toEqual([2024, null, null]);
  });
});
