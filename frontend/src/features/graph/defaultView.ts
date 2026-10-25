import { storyById } from "./lab/views";

/** Home blob fields the graph reads (the share builder's `home`, see backend kb.share.home). */
type EmbeddedHome = { view?: string | null } | undefined;

/**
 * The view the graph opens on: the URL's `?view=` when present, else — once, on first mount — the
 * `home.view` a snapshot was built with (`share snapshot … --view <id>` → `KB_EMBEDDED.home.view`).
 * Unknown ids are ignored, so a stale snapshot never breaks the screen.
 */
export function initialView(
  searchView: string | undefined,
  home: EmbeddedHome = globalThis.KB_EMBEDDED?.home,
  isKnown: (id: string) => boolean = (id) => !!storyById(id),
): string | undefined {
  const id = searchView ?? home?.view ?? undefined;
  return id && isKnown(id) ? id : undefined;
}

/** `?view=<id>` for the Home → Graph links when a snapshot carries a default view (else untouched). */
export function withDefaultView<T extends Record<string, string>>(search: T, home: EmbeddedHome = globalThis.KB_EMBEDDED?.home): T {
  const view = home?.view;
  return view && !("view" in search) ? { ...search, view } : search;
}
