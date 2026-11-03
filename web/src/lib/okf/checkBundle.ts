// checkBundle: the OKF v0.2 bundle gate of src/kb_distillery/lint/okf_check.py, ported to pure TypeScript so the
// deployed site (a Cloudflare Worker) and the browser give an import preview the same verdict as the local app.
//
// The Python module is the source of truth: same rules, same messages, same report as `distill kb import`'s dry run
// builds from it (`"<rel>: [<rule>] <message>"`, sorted by page). tests/lint/test_okf_check_parity.py and
// checkBundle.test.ts run both on the shared bundles in tests/fixtures/okf-bundles/ against one expected report each,
// so the two cannot drift. Change a rule in one place and the other test fails until it follows.
//
// No Node, no DOM: files in, report out. The only dependency is js-yaml (the YAML 1.1 scalar rules of PyYAML are in
// pyCompat.ts). A differential run of 11,500 random bundles against okf_check.py found two diffs, both a YAML anchor
// defined twice (PyYAML refuses it, js-yaml allows it). Known gaps against Python, none reachable by a normal bundle:
//   - YAML: a repeated anchor, non-string mapping keys, `!!binary`/`!!set` tags, integers above 2^53, tabs inside block
//     scalars (read as a syntax error here) and other documents PyYAML and js-yaml parse differently.
//   - Unicode: `\w`, `lower()` and `isprintable()` follow the Unicode tables of the JS engine, not of CPython.
//   - A linked file outside the bundle (`../x.md` above the root) never exists here; Python looks at the disk.
//   - A decode error of a file over 8 KiB reports its position within Python's read chunk, which is not mirrored.
import { PyError, isDict, normpath, pyRepr, pyStr, pyTruthy, cmpCodePoints, readText, safeLoad } from "./pyCompat";
import { PyDate, PyDateTime } from "./pyCompat";
import type { PyDict, PyValue } from "./pyCompat";

export type BundleFiles = Map<string, string | Uint8Array>;
export interface BundleReport {
  /** Suggested kb id, from `opts.name` (the zip stem or folder name); "imported-kb" when it has none. */
  id: string;
  /** Pages counted by okf-check (every .md file but index.md / log.md). */
  pages: number;
  /** Findings that block an import: `"<page>: [<rule>] <message>"`, sorted by page. */
  errors: string[];
  warnings: string[];
}

const WIKI = "wiki";                                    // the bundle root: every path is reported as wiki/<path>
const STATUSES = new Set(["draft", "stable", "deprecated"]);
const RESERVED = new Set(["index.md", "log.md"]);
const SKIP_DIRS = new Set(["raw", "think", "meta", "digest", ".git"]);
const CODE = /^\s*(?:>\s*)*(```|~~~).*?^\s*(?:>\s*)*\1[^\n]*$|`[^`\n]+`/gms;
const MD_LINK = /(?<!!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
const OFFSET = /(?:Z|[+-]\d{2}:?\d{2})$/;
const HEADING = /^#{1,6}\s+([^\n]+?)\s*#*\s*$/gm;
const SCHEME = /^[a-z][a-z0-9+.-]*:/i;

// vault/links.py: the regions of a page that are not prose.
const WIKILINK_ANY = /(!?)\[\[([^\[\]\n]+)\]\]/g;
const PROTECTED = new RegExp(
  "(?:^[ \\t]{0,3}(?<f>`{3,}|~{3,})[^\\n]*\\n(?:.*?\\n)?[ \\t]{0,3}\\k<f>[ \\t]*$|^[ \\t]{0,3}(?:`{3,}|~{3,})[^\\n]*\\n.*(?![\\s\\S]))"
  + "|(?<t>`+)(?:(?!\\n[ \\t]*\\n).)+?(?<!`)\\k<t>(?!`)"
  + "|<!--.*?-->"
  + "|\\$\\$.+?\\$\\$"
  + "|(?<![\\\\$])\\$(?!\\s)[^$\\n]+?(?<!\\s)\\$(?!\\d)", "gms");
const NOTES_HEAD = /^## My notes[ \t]*$/gm;

function notesSpans(body: string): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  for (const m of body.matchAll(NOTES_HEAD)) {
    const next = /^## /gm;
    next.lastIndex = m.index + m[0].length;
    const n = next.exec(body);
    out.push([m.index, n ? n.index : body.length]);
  }
  return out;
}

function protectedSpans(body: string): Array<[number, number]> {
  const spans = notesSpans(body);
  for (const m of body.matchAll(PROTECTED)) spans.push([m.index, m.index + m[0].length]);
  spans.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const merged: Array<[number, number]> = [];
  for (const [a, b] of spans) {
    const last = merged[merged.length - 1];
    if (last && a <= last[1]) last[1] = Math.max(last[1], b);
    else merged.push([a, b]);
  }
  return merged;
}

function prose(body: string): string {
  let out = "";
  let last = 0;
  for (const [a, b] of protectedSpans(body)) {
    out += body.slice(last, a) + body.slice(a, b).replace(/[^\n]/g, " ");
    last = b;
  }
  return out + body.slice(last);
}

const leftoverWikilinks = (body: string) => Array.from(prose(body).matchAll(WIKILINK_ANY), (m) => m[0]);

// -- okf_check.py -----------------------------------------------------------------------------------------------------
function slugify(heading: string): string {
  return heading.trim().toLowerCase().replace(/[^\p{L}\p{N}_\s-]/gu, "").replace(/\s/g, "-");
}

function frontMatter(text: string): [PyDict | null, string] {
  if (!text.startsWith("---\n")) return [null, text];
  const end = text.indexOf("\n---\n", 3);
  if (end === -1) return [null, text];
  const fm = safeLoad(text.slice(4, end));
  const body = text.slice(end + 5);
  return fm !== undefined && isDict(fm) ? [fm, body] : [null, body];
}

function hasOffset(value: PyValue): boolean {
  if (value instanceof PyDateTime) return value.tz !== null;
  if (value instanceof PyDate) return false;
  return OFFSET.test(pyStr(value).trim());
}

const headings = (body: string) => new Set(Array.from(body.replace(CODE, "").matchAll(HEADING), (m) => slugify(m[1]!)));
const basename = (p: string) => p.slice(p.lastIndexOf("/") + 1);
const isReserved = (rel: string) => RESERVED.has(basename(rel));
type Finding = [string, string];

class Bundle {
  private dirs = new Set<string>();
  private texts = new Map<string, string | PyError>();

  constructor(readonly files: BundleFiles) {
    for (const key of files.keys()) {
      for (let i = key.indexOf("/"); i !== -1; i = key.indexOf("/", i + 1)) this.dirs.add(key.slice(0, i));
    }
  }

  /** The key of the file `target` (a path from the kb root) names, as the OS would resolve it, else null. Only
   *  `wiki/` exists beside it, so a path elsewhere is never a file. */
  resolve(target: string): string | null {
    if (target.endsWith("/")) return null;
    const segs = target.split("/").filter((s) => s !== "" && s !== ".");
    const stack: string[] = [];
    for (const [i, seg] of segs.entries()) {
      if (seg === "..") {
        if (!stack.length) return null;
        stack.pop();
        continue;
      }
      stack.push(seg);
      if (i < segs.length - 1) {                                        // a directory on the way must exist
        const below = stack.slice(1).join("/");
        if (stack[0] !== WIKI || (stack.length > 1 && !this.dirs.has(below))) return null;
      }
    }
    if (stack[0] !== WIKI) return null;
    const key = stack.slice(1).join("/");
    return this.files.has(key) ? key : null;
  }

  /** The text of a file as Python reads it; a file that does not decode throws the UnicodeDecodeError every time. */
  text(key: string): string {
    let hit = this.texts.get(key);
    if (hit === undefined) {
      try {
        hit = readText(this.files.get(key)!);
      } catch (e) {
        if (!(e instanceof PyError)) throw e;
        hit = e;
      }
      this.texts.set(key, hit);
    }
    if (hit instanceof PyError) throw hit;
    return hit;
  }

  checkPage(rel: string, text: string): Finding[] {
    const out: Finding[] = [];
    const [fm, body] = frontMatter(text);
    if (!isReserved(rel)) {
      if (fm === null || !pyStr(pyTruthy(fm.type) ? fm.type : "").trim()) out.push(["type", "no parseable non-empty `type`"]);
      if (fm && Object.keys(fm).length) {
        if ("status" in fm && !STATUSES.has(pyStr(fm.status))) {
          out.push(["status", `status ${pyRepr(fm.status)} is not draft, stable or deprecated`]);
        }
        let srcs: PyValue = pyTruthy(fm.sources) ? fm.sources! : [];
        if (!Array.isArray(srcs)) {
          out.push(["sources", `\`sources\` is not a list: ${pyRepr(srcs)}`]);
          srcs = [];
        }
        for (const entry of srcs) {
          if (!(isDict(entry) && pyTruthy(entry.resource))) out.push(["sources", `source entry without \`resource\`: ${pyRepr(entry)}`]);
        }
        const stamps: Array<[string, PyValue]> = [];
        for (const k of ["created", "updated"]) if (k in fm) stamps.push([k, fm[k]!]);
        const gen = fm.generated;
        if (isDict(gen) && "at" in gen) stamps.push(["generated.at", gen.at!]);
        for (const [key, value] of stamps) {
          if (!hasOffset(value)) out.push(["timestamp", `${key} ${pyRepr(value)} has no UTC offset`]);
        }
      }
    }
    if (basename(rel) !== "log.md") {
      for (const found of [...new Set(leftoverWikilinks(body))].sort(cmpCodePoints)) out.push(["wikilink", found]);
    }
    const own = headings(body);
    const dir = rel.slice(0, rel.lastIndexOf("/"));
    for (const m of prose(body).matchAll(MD_LINK)) {
      const href = m[1]!;
      if (SCHEME.test(href)) continue;                                  // http:, mailto:
      const hash = href.indexOf("#");
      const path = hash === -1 ? href : href.slice(0, hash);
      const anchor = hash === -1 ? "" : href.slice(hash + 1);
      let target: string;
      if (path.startsWith("/")) target = path.replace(/^\/+/, "");
      else if (path) target = normpath(`${dir}/${path}`);
      else target = rel;
      const top = target.split("/", 1)[0];
      if (top === "raw" || top === "think") {
        out.push(["boundary", `link into ${top}/: ${href}`]);
        continue;
      }
      const key = this.resolve(target);
      if (key === null) out.push(["link", `unresolved: ${href}`]);
      else if (anchor && target.endsWith(".md")) {
        const heads = target === rel ? own : headings(frontMatter(this.text(key))[1]);
        if (!heads.has(anchor.toLowerCase())) out.push(["link", `unresolved anchor: ${href}`]);
      }
    }
    return out;
  }
}

/** import_kb's default_id: a kb id from a source name. */
function suggestId(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40).replace(/^-+|-+$/g, "");
  return slug && /^[a-z0-9]/.test(slug) ? slug : "imported-kb";
}

/**
 * Check an OKF bundle. `files` maps a path inside the bundle root (what the local app calls `wiki/`, so `a.md` and
 * `sub/b.md`, no leading slash) to its text or bytes. Returns what `distill kb import` shows before it writes anything.
 */
export function checkBundle(files: BundleFiles, opts: { name?: string } = {}): BundleReport {
  const bundle = new Bundle(files);
  const found = new Map<string, Finding[]>();
  let pages = 0;
  for (const key of files.keys()) {
    const parts = key.split("/");
    if (!key.endsWith(".md") || parts.slice(0, -1).some((d) => SKIP_DIRS.has(d) || d.startsWith("."))) continue;
    const rel = `${WIKI}/${key}`;
    if (!isReserved(rel)) pages++;
    let findings: Finding[];
    try {
      findings = bundle.checkPage(rel, bundle.text(key));
    } catch (e) {                                                       // a bad page is a finding, never a crash
      if (!(e instanceof PyError)) throw e;
      findings = [["read", String(e)]];
    }
    if (findings.length) found.set(rel, findings);
  }
  const errors = [...found.keys()].sort(cmpCodePoints)
    .flatMap((rel) => found.get(rel)!.map(([rule, msg]) => `${rel}: [${rule}] ${msg}`));
  if (!pages && !errors.length) errors.push("the bundle has no pages (no .md files besides index.md / log.md)");
  return { id: suggestId(opts.name ?? ""), pages, errors, warnings: [] };
}
