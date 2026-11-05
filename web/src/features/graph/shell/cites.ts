/** `[Title](slug.md)` or `[Title](slug.md#heading)`: how an answer links a wiki page (the same shape the Markdown renderer routes). */
const PAGE_LINK = /\]\(\s*([^/:#?()\s]+)\.md(?:#[^)\s]*)?\s*\)/g;
const WIKILINK = /\[\[([^\[\]|\n]+?)(?:\|[^\[\]\n]+?)?\]\]/g;

const decode = (s: string): string => {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
};

/** The pages an answer links, once each, in order of first mention. */
export function citedSlugs(markdown: string): string[] {
  const hits: { at: number; slug: string }[] = [];
  for (const m of markdown.matchAll(PAGE_LINK)) hits.push({ at: m.index, slug: decode(m[1]!) });
  for (const m of markdown.matchAll(WIKILINK)) hits.push({ at: m.index, slug: m[1]!.trim() });
  hits.sort((a, b) => a.at - b.at);
  return [...new Set(hits.map((h) => h.slug))];
}

/** The slug a rendered page link points at (`/app/pages/<slug>`), or null for any other link. */
export function slugOfHref(href: string | null): string | null {
  const m = /\/pages\/([^/?#]+)/.exec(href ?? "");
  return m ? decode(m[1]!) : null;
}
