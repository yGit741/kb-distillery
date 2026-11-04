// Parity with src/kb_distillery/lint/okf_check.py: every bundle in tests/fixtures/okf-bundles/ must give the report in
// its expected.json, the one tests/lint/test_okf_check_parity.py asserts for the Python checker.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";
import { checkBundle } from "./checkBundle";
import type { BundleFiles } from "./checkBundle";

const FIXTURES = join(__dirname, "../../../../tests/fixtures/okf-bundles");
const RULES = ["type", "status", "sources", "timestamp", "wikilink", "link", "boundary", "read"];

const cases = readdirSync(FIXTURES).filter((n) => statSync(join(FIXTURES, n)).isDirectory()).sort();

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

/** The bundle as bytes keyed by its path below bundle/, which the checker mounts as wiki/. */
function load(name: string): BundleFiles {
  const root = join(FIXTURES, name, "bundle");
  return new Map(walk(root).map((p) => [relative(root, p).split("\\").join("/"), new Uint8Array(readFileSync(p))]));
}

const expected = (name: string) => JSON.parse(readFileSync(join(FIXTURES, name, "expected.json"), "utf-8"));

describe("checkBundle parity with okf_check", () => {
  it("finds the shared fixtures", () => {
    expect(cases.length).toBeGreaterThan(10);
  });

  it.each(cases)("%s", (name) => {
    const { id, name: shown, ...report } = checkBundle(load(name));
    expect(id).toBe("imported-kb");
    expect(shown).toBe("Imported kb");
    expect(report).toEqual(expected(name));
  });

  it("covers every rule of the checker", () => {
    const seen = new Set(cases.flatMap((n) => expected(n).errors as string[]).map((e) => /^[^[]*\[([a-z]+)\]/.exec(e)?.[1]));
    for (const rule of RULES) expect(seen.has(rule), rule).toBe(true);
  });

  it("gives the same report for text as for bytes", () => {
    const enc = new TextEncoder();
    const text: BundleFiles = new Map<string, string | Uint8Array>([
      ["a.md", "---\ntype: idea\n---\n\n[b](b.md)\n"],
      ["b.md", enc.encode("---\ntype: idea\r\n---\r\n\r\n# B\r\n")],
    ]);
    expect(checkBundle(text)).toEqual({ id: "imported-kb", name: "Imported kb", pages: 2, errors: [], warnings: [] });
  });

  it("suggests a kb id from the source name like the import does", () => {
    const files: BundleFiles = new Map([["a.md", "---\ntype: t\n---\n"]]);
    expect(checkBundle(files, { name: "My Notes (2026)!" }).id).toBe("my-notes-2026");
    expect(checkBundle(files, { name: "---" }).id).toBe("imported-kb");
    expect(checkBundle(files, { name: "x".repeat(60) }).id).toBe("x".repeat(40));
  });

  // tests/fixtures/okf-bundles/names.json is also asserted by test_okf_check_parity.py against import_kb.default_id
  it.each(JSON.parse(readFileSync(join(FIXTURES, "names.json"), "utf-8")) as Array<{ source: string; kind: string; id: string; name: string }>)(
    "names $source ($kind) like the local import",
    ({ source, kind, id, name }) => {
      const files: BundleFiles = new Map([["a.md", "---\ntype: t\n---\n"]]);
      const r = checkBundle(files, { name: source, archive: kind === "file" });
      expect([r.id, r.name]).toEqual([id, name]);
    },
  );
});
