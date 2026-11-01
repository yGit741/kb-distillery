/**
 * The one place the frontend knows how a page link is written. Mirrors src/kb_distillery/core/links.py.
 *
 * Today pages link with wikilinks (`[[slug]]`, `[[slug|label]]`, `[[slug#heading]]`). `toLlm` and
 * `toDisk` are the identity until the on-disk link form changes (OKF PR8): that switch then happens
 * in these functions only, and no caller changes.
 */

/** Target slug only: `[[slug` up to `|`, `#`, `]` or an escaped pipe. Global; reset `lastIndex` or use matchAll. */
export const WIKILINK_TARGET = /\[\[([^\]|#\\]+)/g;

/** Whole link with groups (slug, label). A `#heading` part is allowed and dropped. Global. */
export const WIKILINK = /\[\[([^\]|#\\]+)(?:#[^\]|]+)?(?:\\?\|([^\]]+))?\]\]/g;

/** Stripped link targets of `text`, in order, duplicates kept. */
export function targets(text: string): string[] {
  return Array.from((text ?? "").matchAll(WIKILINK_TARGET), (m) => m[1]!.trim());
}

/** Page text as shown to a model or a reader. */
export const toLlm = (text: string): string => text;

/** Text as a writer stores it in a page. */
export const toDisk = (text: string): string => text;
