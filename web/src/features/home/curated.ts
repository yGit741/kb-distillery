import type { CardDef } from "./samplers";

/**
 * Hand-picked Home cards (share.toml `[home] cards`, baked into the share blob). Anything malformed is
 * dropped rather than shown.
 */
export function parseCards(raw: unknown): CardDef[] {
  if (!Array.isArray(raw)) return [];
  const out: CardDef[] = [];
  for (const c of raw) {
    if (!c || typeof c !== "object") continue;
    const o = c as Record<string, unknown>;
    const pages = Array.isArray(o.pages) ? o.pages.filter((p): p is string => typeof p === "string" && !!p) : [];
    if (typeof o.title !== "string" || !o.title || !pages.length) continue;
    out.push({
      title: o.title,
      pages,
      focus: typeof o.focus === "string" ? o.focus : undefined,
      caption: typeof o.caption === "string" ? o.caption : undefined,
    });
  }
  return out;
}

/** A share build's cards come from its blob (share.toml `[home]`, kb_distillery.share.home); the local app has none. */
export const curatedCards = (): CardDef[] =>
  parseCards(globalThis.KB_EMBEDDED?.home?.cards ?? (globalThis as { KB_HOME_CARDS?: unknown }).KB_HOME_CARDS);
