import { notesSpans, type BundleFiles } from "@/lib/okf/checkBundle";

export interface SourcePage {
  slug: string;
  source: string;
}
export interface BundleOpts {
  /** Most pages in the bundle; the lowest-degree ones are cut past it. Default 60. */
  cap?: number;
  includeNotes: boolean;
  kbName?: string;
}
export interface Bundle {
  /** The pasteable text: a header, then one `--- wiki/<path> ---` block per file. */
  text: string;
  /** The same content as a bundle (paths inside wiki/), for okf-check. */
  files: BundleFiles;
  /** Slugs left out because of the cap, lowest degree first. */
  cut: string[];
}

export const DEFAULT_CAP = 60;
const NAMED_CUTS = 8;
const OKF_VERSION = "0.2";
const LINK = /(?<!!)\]\(([^)\s#]+)\.md(?:#[^)\s]*)?\)/g;

/** Remove every `## My notes` section (to the next `## ` heading, as the checker reads it). */
export function stripNotes(source: string): string {
  const spans = notesSpans(source);
  let out = source;
  for (const [a, b] of spans.reverse()) out = out.slice(0, a) + out.slice(b);
  return out.replace(/\n{3,}/g, "\n\n").replace(/\s+$/, "") + "\n";
}

const titleOf = (source: string, slug: string): string => {
  const m = /^title:[ \t]*["']?(.+?)["']?[ \t]*$/m.exec(source.startsWith("---\n") ? source.slice(0, source.indexOf("\n---\n", 3) + 1 || 0) : "");
  return m ? m[1]! : slug;
};

function degrees(pages: SourcePage[]): Map<string, number> {
  const slugs = new Set(pages.map((p) => p.slug));
  const deg = new Map(pages.map((p) => [p.slug, 0]));
  for (const p of pages) {
    for (const m of p.source.matchAll(LINK)) {
      const to = m[1]!;
      if (to === p.slug || !slugs.has(to)) continue;
      deg.set(p.slug, deg.get(p.slug)! + 1);
      deg.set(to, deg.get(to)! + 1);
    }
  }
  return deg;
}

export function buildBundle(pages: SourcePage[], opts: BundleOpts): Bundle {
  const cap = opts.cap ?? DEFAULT_CAP;
  const unique = [...new Map(pages.map((p) => [p.slug, p])).values()];
  const deg = degrees(unique);
  const ranked = [...unique].sort((a, b) => deg.get(b.slug)! - deg.get(a.slug)! || (a.slug < b.slug ? -1 : 1));
  const keep = new Set(ranked.slice(0, cap).map((p) => p.slug));
  const cut = ranked.slice(cap).map((p) => p.slug);
  const kept = unique.filter((p) => keep.has(p.slug)).map((p) => ({ slug: p.slug, source: opts.includeNotes ? p.source : stripNotes(p.source) }));

  const index = [
    "---",
    `okf_version: ${OKF_VERSION}`,
    "---",
    "",
    "# Wiki index",
    "",
    ...kept.map((p) => `- [${titleOf(p.source, p.slug)}](${p.slug}.md)`),
    "",
  ].join("\n");

  const files: BundleFiles = new Map([["index.md", index], ...kept.map((p): [string, string] => [`${p.slug}.md`, p.source])]);
  const blocks = [...files].map(([path, text]) => `--- wiki/${path} ---\n${(text as string).replace(/\n*$/, "\n")}`);
  const lines = [`# OKF bundle · ${kept.length} pages · ${opts.kbName ?? "Knowledge Base"}`, "", blocks.join("\n")];
  if (cut.length) {
    const named = cut.slice(0, NAMED_CUTS).join(", ");
    lines.push(`${cut.length} pages not included: ${named}${cut.length > NAMED_CUTS ? ", …" : ""}`);
  }
  return { text: lines.join("\n").replace(/\n*$/, "\n"), files, cut };
}
