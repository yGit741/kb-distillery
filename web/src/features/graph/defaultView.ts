import { storyById } from "./lab/views";

/** Home blob fields the graph reads (the share builder's `home`, see backend kb_distillery.share.home). */
type EmbeddedHome = { view?: string | null } | undefined;

/** URL params that describe a dive of their own (a Home card, a focus, a search …): a snapshot's default
 *  view must not re-filter them through Map. */
export const DIVE_PARAMS = ["pages", "focus", "select", "search", "scope"] as const;

const hasDive = (search: Record<string, unknown>): boolean => DIVE_PARAMS.some((k) => search[k] !== undefined && search[k] !== "");

/**
 * The view the graph opens on: the URL's `?view=` when present, else — once, on first mount, and only on a
 * bare link (no dive params) — the `home.view` a snapshot was built with (`share snapshot … --view <id>` →
 * `KB_EMBEDDED.home.view`). Unknown ids are ignored, so a stale snapshot never breaks the screen.
 */
export function initialView(
  search: Record<string, unknown> & { view?: string },
  home: EmbeddedHome = globalThis.KB_EMBEDDED?.home,
  isKnown: (id: string) => boolean = (id) => !!storyById(id),
): string | undefined {
  const id = search.view ?? (hasDive(search) ? undefined : home?.view) ?? undefined;
  return id && isKnown(id) ? id : undefined;
}

/** `?view=<id>` for the Home → Graph links when a snapshot carries a default view and the link is bare (no dive). */
export function withDefaultView<T extends Record<string, string>>(search: T, home: EmbeddedHome = globalThis.KB_EMBEDDED?.home): T {
  const view = home?.view;
  return view && !("view" in search) && !hasDive(search) ? { ...search, view } : search;
}
