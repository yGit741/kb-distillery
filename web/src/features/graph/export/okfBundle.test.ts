import { checkBundle } from "@/lib/okf/checkBundle";
import { buildBundle, stripNotes } from "./okfBundle";

const page = (slug: string, body: string, title = slug) =>
  ({ slug, source: `---\ntype: idea\ntitle: ${title}\nupdated: 2026-01-02T03:04:05+00:00\n---\n\n# ${title}\n\n${body}\n` });

const A = page("alpha", "See [Beta](beta.md) and [Gamma](gamma.md).\n\n## My notes\n\nprivate thought [x](nowhere.md)\n");
const B = page("beta", "Back to [Alpha](alpha.md).");
const C = page("gamma", "Links [Beta](beta.md), and [Outside](outside.md).");

describe("buildBundle", () => {
  it("writes the header, a generated index and one block per page", () => {
    const b = buildBundle([A, B, C], { includeNotes: true, kbName: "Demo" });
    const lines = b.text.split("\n");
    expect(lines[0]).toBe("# OKF bundle · 3 pages · Demo");
    expect(b.text).toContain("--- wiki/index.md ---\n---\nokf_version: 0.2\n---");
    expect(b.text).toContain("- [alpha](alpha.md)");
    for (const s of ["alpha", "beta", "gamma"]) expect(b.text).toContain(`--- wiki/${s}.md ---\n---\ntype: idea`);
    expect(b.cut).toEqual([]);
  });

  it("keeps the notes only when asked", () => {
    expect(buildBundle([A], { includeNotes: true }).text).toContain("private thought");
    const b = buildBundle([A], { includeNotes: false });
    expect(b.text).not.toContain("private thought");
    expect(b.text).not.toContain("My notes");
    expect(b.files.get("alpha.md")).toContain("See [Beta](beta.md)");
  });

  it("stripNotes drops only the notes section", () => {
    expect(stripNotes("a\n\n## My notes\n\nx\n\n## After\n\ny\n")).toBe("a\n\n## After\n\ny\n");
  });

  it("passes the checker; a link outside the set stays and is the only finding", () => {
    const closed = buildBundle([A, B, { ...C, source: C.source.replace(", and [Outside](outside.md)", "") }], { includeNotes: false });
    expect(checkBundle(closed.files).errors).toEqual([]);
    const open = buildBundle([A, B, C], { includeNotes: false });
    expect(open.text).toContain("[Outside](outside.md)");
    expect(checkBundle(open.files).errors).toEqual(["wiki/gamma.md: [link] unresolved: outside.md"]);
  });

  it("cuts the lowest degree past the cap and names them", () => {
    const lone = ["l1", "l2", "l3"].map((s) => page(s, "alone"));
    const b = buildBundle([...lone, A, B, C], { cap: 3, includeNotes: false });
    expect(b.cut).toEqual(["l1", "l2", "l3"]);
    expect(b.text).toContain("# OKF bundle · 3 pages");
    expect(b.text.trimEnd().split("\n").pop()).toBe("3 pages not included: l1, l2, l3");
    expect([...b.files.keys()].sort()).toEqual(["alpha.md", "beta.md", "gamma.md", "index.md"]);
  });
});
