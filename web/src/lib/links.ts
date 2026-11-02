/**
 * The one place the frontend knows how a page link is written. Mirrors src/kb_distillery/core/links.py.
 *
 * On disk a page links to another with a relative markdown link, `[Title](slug.md)` (`[label](slug.md#heading)` for a
 * heading; Open Knowledge Format v0.2, `wiki/` is flat). Wikilinks (`[[slug]]`, `[[slug|label]]`, `[[slug#heading]]`)
 * survive only in a page's `## My notes`; `targets` reads both, so a graph or backlink view loses no edge.
 */

/** Target slug only: `[[slug` up to `|`, `#`, `]` or an escaped pipe. Global; reset `lastIndex` or use matchAll. */
export const WIKILINK_TARGET = /\[\[([^\]|#\\]+)/g;

/** Whole wikilink with groups (slug, label). A `#heading` part is allowed and dropped. Global. */
export const WIKILINK = /\[\[([^\]|#\\]+)(?:#[^\]|]+)?(?:\\?\|([^\]]+))?\]\]/g;

/** A page link with groups (label, slug, anchor). The label may hold escaped brackets. Global. */
export const PAGE_LINK = /(?<!!)\[((?:[^[\]\\\n]|\\.)*)\]\(([^()<>\s/:#]+?)\.md(?:#([^()\s]*))?\)/g;

const LINK_TARGET = /\[\[([^\]|#\\]+)|(?<!!)\[(?:[^[\]\\\n]|\\.)*\]\(([^()<>\s/:#]+?)\.md[)#]/g;

/** Stripped slugs `text` links to, in order, duplicates kept: page links and (My notes) wikilinks. */
export function targets(text: string): string[] {
  return Array.from((text ?? "").matchAll(LINK_TARGET), (m) => (m[1] ?? m[2])!.trim());
}

/** Link text that reads as the literal `label`: backslash and square brackets escaped. */
export const escapeLabel = (label: string): string => label.replace(/([\\[\]])/g, "\\$1");

/** GitHub-style anchor of a heading (`Why it works` -> `why-it-works`). */
export const slugify = (heading: string): string => heading.trim().toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s/g, "-");

/** `[label](slug.md#anchor)`: how a writer links a page. `label` defaults to the slug. */
export function link(slug: string, label?: string, anchor?: string): string {
  const text = escapeLabel((label ?? slug).split(/\s+/).filter(Boolean).join(" "));
  return `[${text}](${slug}.md${anchor ? "#" + slugify(anchor) : ""})`;
}

/** `text` with each page link and wikilink reduced to its label (a bare wikilink to its slug). */
export function plain(text: string): string {
  return (text ?? "")
    .replace(PAGE_LINK, (_m, label: string) => label.replace(/\\(.)/g, "$1"))
    .replace(WIKILINK, (_m, slug: string, label?: string) => (label ?? slug).trim());
}

/** Page text as shown to a model or a reader: the markdown a person reads (identity). */
export const toLlm = (text: string): string => text;

/** Text as a writer stores it in a page (identity: writers build links with `link`). */
export const toDisk = (text: string): string => text;
