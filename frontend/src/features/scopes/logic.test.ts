import { DRAFTS_KEY, NO_FILTER, checkSave, corpusToRow, filterRows, matchPages, matchRaw, newRows, normSlug, readDrafts, dropDraft, snapshot, stats, type ScopeRow } from "./logic";

const row = (path: string, o: Partial<ScopeRow> = {}): ScopeRow => ({
  path, format: path.split("/")[1] ?? "", disposition: "queued", slug: null, page_type: null, digestion: "", collection: [], year: null, ...o,
});

function memStore(init?: string) {
  const m = new Map<string, string>(init ? [[DRAFTS_KEY, init]] : []);
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
}

describe("scope logic", () => {
  it("normalises slugs", () => {
    expect(normSlug(" My Topic! ")).toBe("scope-my-topic");
    expect(normSlug("scope-x")).toBe("scope-x");
    expect(normSlug("  ")).toBe("");
  });

  it("filters rows by undigested, format, collection and text", () => {
    const rows = [
      row("raw/printed-docs/a.pdf", { disposition: "digested", collection: ["course-rl"] }),
      row("raw/handwritten/b.pdf", { collection: ["course-rl"] }),
      row("raw/printed-docs/c.pdf", { slug: "paper-c" }),
    ];
    expect(filterRows(rows, { ...NO_FILTER, undigested: true })).toHaveLength(2);
    expect(filterRows(rows, { ...NO_FILTER, formats: new Set(["handwritten"]) })).toHaveLength(1);
    expect(filterRows(rows, { ...NO_FILTER, collections: new Set(["course-rl"]) })).toHaveLength(2);
    expect(filterRows(rows, { ...NO_FILTER, text: "PAPER-C" })).toHaveLength(1);
  });

  it("computes stats, new rows and the dirty snapshot independent of order", () => {
    const a = row("raw/x/a", { disposition: "digested" });
    const b = row("raw/x/b");
    expect(stats([row("raw/x/s", { disposition: "source" }), row("raw/x/p", { disposition: "partial" }), row("raw/x/k", { disposition: "skip" })]).digested).toBe(2);
    expect(stats([a, b])).toEqual({ files: 2, digested: 1, pct: 50 });
    expect(stats([])).toEqual({ files: 0, digested: 0, pct: 0 });
    expect(newRows([a], [a, b, b])).toEqual([b]);
    expect(snapshot("t", "w", [a, b])).toBe(snapshot(" t ", "w ", [b, a]));
  });

  it("validates a save", () => {
    expect(checkSave(true, "", "T", "w").error).toMatch(/slug/);
    expect(checkSave(true, "x", " ", "w").error).toMatch(/title/);
    expect(checkSave(false, "scope-x", "T", " ").error).toMatch(/Why/);
    expect(checkSave(true, "my set", "T", "w")).toEqual({ slug: "scope-my-set", error: null });
  });

  it("matches pages and raw files, skipping files already in the scope", () => {
    const cards = [{ id: "paper-a", title: "Alpha net" }, { id: "idea-b", title: "Beta" }] as unknown as Parameters<typeof matchPages>[0];
    expect(matchPages(cards, "alpha").map((c) => c.id)).toEqual(["paper-a"]);
    expect(matchPages(cards, "")).toEqual([]);
    const files = [row("raw/printed-docs/2020-a.pdf"), row("raw/printed-docs/2021-a.pdf"), row("raw/images/a-01.png", { disposition: "asset:raw/web-clips/a.md" })];
    expect(matchRaw(files, new Set(["raw/printed-docs/2020-a.pdf"]), "a.pdf").map((r) => r.path)).toEqual(["raw/printed-docs/2021-a.pdf"]);
  });

  it("maps a corpus row", () => {
    const r = corpusToRow({ path: "raw/emails/t/thread.md", collection: ["x"], digestion: "", sha1: "", title: "", disposition: null }, "emails");
    expect(r).toMatchObject({ format: "emails", disposition: "queued", collection: ["x"] });
  });

  it("reads and drops drafts in the graph's localStorage format", () => {
    const st = memStore(JSON.stringify({ active: "k", drafts: { k: { slug: "scope-k", title: "K", isNew: true, rows: [] } } }));
    expect(readDrafts(st).drafts.k?.title).toBe("K");
    dropDraft("k", st);
    expect(readDrafts(st)).toEqual({ active: "", drafts: {} });
    expect(readDrafts(memStore("not json"))).toEqual({ active: "", drafts: {} });
  });
});
