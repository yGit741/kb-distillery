import { buildUnits, canDigest, countUnits, filterUnits, groupByMonth, groupUnits, parseSnapshot, previewKind, rawThumbUrl, resolveRawUrl } from "./items";
import { snapshot } from "./fixtures";

const data = parseSnapshot(snapshot);

describe("pipeline items", () => {
  it("folds companions into one unit per thread", () => {
    expect(data.units).toHaveLength(6);
    const thread = data.units.find((u) => u.isThread)!;
    expect(thread.files).toHaveLength(2);
    expect(thread.name).toBe("t");
  });

  it("derives status and depth from the model, never a catalog depth", () => {
    const by = Object.fromEntries(data.units.map((u) => [u.name, u]));
    expect(by["2020-easy.pdf"]).toMatchObject({ status: "digested", depth: "easy" });
    expect(by["2022-listed.pdf"]).toMatchObject({ status: "undigested", depth: "listed" });
    expect(by["queued.md"]).toMatchObject({ status: "undigested", depth: "", backlog: true });
    expect(by["new.pdf"]).toMatchObject({ status: "inbox" });
  });

  it("counts statuses, depths and backlog", () => {
    const c = countUnits(data.units);
    expect(c.status.digested).toBe(2);
    expect(c.depth).toEqual({ listed: 1, easy: 1, full: 0, deep: 1 });
    expect(c.cataloged).toBe(5);
    expect(c.backlog).toBe(3);
  });

  it("filters by format, depth, status, collection, backlog and text", () => {
    const n = (f: Parameters<typeof filterUnits>[1]) => filterUnits(data.units, f).length;
    expect(n({ format: "printed-docs" })).toBe(3);
    expect(n({ depth: "deep" })).toBe(1);
    expect(n({ status: "cataloged" })).toBe(5);
    expect(n({ status: "inbox" })).toBe(1);
    expect(n({ collection: "course-x" })).toBe(2);
    expect(n({ collection: "@none" })).toBe(4);
    expect(n({ backlog: true })).toBe(3);
    expect(n({ q: "course x" })).toBe(2);
    expect(n({ q: "nothing-matches" })).toBe(0);
  });

  it("groups by status in pipeline order and by month newest first", () => {
    expect(groupUnits(data.units, "status", data.titles).map(([k]) => k)).toEqual(["inbox", "undigested", "digested"]);
    expect(groupByMonth(data.units).map(([k]) => k)).toEqual(["2026-10", "2026-09", "unknown"]);
  });

  it("only offers a digest for a cataloged, undigested file with a preview type", () => {
    const by = Object.fromEntries(data.units.map((u) => [u.name, u]));
    expect(canDigest(by["queued.md"]!)).toBe(true);
    expect(canDigest(by["2020-easy.pdf"]!)).toBe(false);
    expect(canDigest(by["new.pdf"]!)).toBe(false);
  });

  it("builds typed raw urls and resolves clip-relative links", () => {
    expect(rawThumbUrl("raw/printed-docs/a b.pdf", 400)).toBe("/api/raw/raw/printed-docs/a%20b.pdf/thumb?w=400");
    expect(resolveRawUrl("../images/x.jpg", "raw/web-clips")).toBe("/api/raw/raw/images/x.jpg/file");
    expect(resolveRawUrl("https://a.b/c", "raw/web-clips")).toBe("https://a.b/c");
    expect(previewKind(".pdf")).toBe("pdf");
    expect(previewKind(".zip")).toBe("none");
  });

  it("tolerates junk rows", () => {
    expect(buildUnits([])).toEqual([]);
    expect(parseSnapshot({ ...snapshot, items: [{ nope: 1 }], failures: "x" as never }).units).toEqual([]);
  });
});
