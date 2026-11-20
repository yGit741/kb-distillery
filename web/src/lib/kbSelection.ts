/**
 * Which knowledge bases the graph shows, as the `?kbs=` URL param (so a presentation link reproduces the view):
 * absent = the server's own (the default), `none` = nothing, else the ids in order. The header menu writes it,
 * the graph reads it.
 */
export const NO_KBS = "none";

/** null = the default (the server's own knowledge base); [] = none. */
export function parseKbs(raw: string | undefined): string[] | null {
  if (raw === undefined || raw === "") return null;
  if (raw === NO_KBS) return [];
  return [...new Set(raw.split(",").map((s) => s.trim()).filter(Boolean))];
}

/** The param for `ids`: undefined when it is just the server's own knowledge base. */
export function formatKbs(ids: readonly string[], active: string | null): string | undefined {
  if (!ids.length) return NO_KBS;
  if (ids.length === 1 && ids[0] === active) return undefined;
  return ids.join(",");
}

/** The knowledge base menus' search line: every whitespace-separated term of `query` is in the name or id (any case). */
export function matchesKb(kb: { id: string; name: string }, query: string): boolean {
  const hay = `${kb.name} ${kb.id}`.toLowerCase();
  return query.toLowerCase().split(/\s+/).filter(Boolean).every((t) => hay.includes(t));
}
