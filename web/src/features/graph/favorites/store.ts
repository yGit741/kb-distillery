import { create } from "zustand";
import { capabilities } from "../shell/capabilities";
import { IS_SHARE } from "@/share/env";
import { useShellStore } from "../shell/shellStore";

/**
 * The favorite pages (flag graph-intent): a kb-level set the server keeps (`/api/favorites`). The store loads it with the
 * graph, flips a page at once and tells the server; a refusal puts the page back with one quiet notice.
 */
export type FavFetch = typeof fetch;

interface FavState {
  slugs: ReadonlySet<string>;
  loaded: boolean;
  /** Read the set (on a graph load and a kb change); a failure leaves it empty and says nothing. */
  load: (kb?: string, f?: FavFetch) => Promise<void>;
  /** Flip one page: optimistic, reverted on error. Does nothing on the share build, which is read-only. */
  toggle: (slug: string, f?: FavFetch) => Promise<void>;
  isFavorite: (slug: string) => boolean;
}

export const FAVORITE_ERROR = "Could not save that favorite.";

const url = (kb?: string) => `/api/favorites${kb ? `?kb=${encodeURIComponent(kb)}` : ""}`;
let loadSeq = 0;

export const useFavorites = create<FavState>((set, get) => ({
  slugs: new Set(),
  loaded: false,
  isFavorite: (slug) => get().slugs.has(slug),
  load: async (kb, f = (...a) => fetch(...a)) => {
    const seq = ++loadSeq;
    // a shared site has no server: the marks are baked into the page
    if (IS_SHARE) return set({ slugs: new Set(globalThis.KB_EMBEDDED?.favorites ?? []), loaded: true });
    try {
      const res = await f(url(kb), { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      const body = (await res.json()) as { slugs?: string[] };
      if (seq === loadSeq) set({ slugs: new Set(body.slugs ?? []), loaded: true });
    } catch {
      if (seq === loadSeq) set({ slugs: new Set(), loaded: false });
    }
  },
  toggle: async (slug, f = (...a) => fetch(...a)) => {
    if (!capabilities().favoriteToggle) return;
    const before = get().slugs;
    const on = !before.has(slug);
    const next = new Set(before);
    if (on) next.add(slug);
    else next.delete(slug);
    set({ slugs: next });
    try {
      const res = on
        ? await f("/api/favorites", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slug }) })
        : await f(`/api/favorites/${encodeURIComponent(slug)}`, { method: "DELETE" });
      if (!res.ok) throw new Error(String(res.status));
    } catch {
      // put back only this page: another toggle may have landed meanwhile
      const now = new Set(get().slugs);
      if (before.has(slug)) now.add(slug);
      else now.delete(slug);
      set({ slugs: now });
      useShellStore.getState().say(FAVORITE_ERROR);
    }
  },
}));
