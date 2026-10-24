import { create } from "zustand";

/**
 * Cross-screen client state: what is selected (graph, pages, scopes all read it) and which scope
 * draft is open. Server data belongs in TanStack Query, URL-worthy state in router search params.
 */
export interface KbState {
  selection: ReadonlySet<string>;
  scopeDraftId: string | null;
  select: (slug: string) => void;
  deselect: (slug: string) => void;
  toggle: (slug: string) => void;
  setSelection: (slugs: Iterable<string>) => void;
  clearSelection: () => void;
  setScopeDraft: (id: string | null) => void;
}

export const useKb = create<KbState>((set) => ({
  selection: new Set<string>(),
  scopeDraftId: null,
  select: (slug) => set((s) => (s.selection.has(slug) ? s : { selection: new Set(s.selection).add(slug) })),
  deselect: (slug) =>
    set((s) => {
      if (!s.selection.has(slug)) return s;
      const next = new Set(s.selection);
      next.delete(slug);
      return { selection: next };
    }),
  toggle: (slug) =>
    set((s) => {
      const next = new Set(s.selection);
      if (!next.delete(slug)) next.add(slug);
      return { selection: next };
    }),
  setSelection: (slugs) => set({ selection: new Set(slugs) }),
  clearSelection: () => set((s) => (s.selection.size ? { selection: new Set() } : s)),
  setScopeDraft: (id) => set({ scopeDraftId: id }),
}));
