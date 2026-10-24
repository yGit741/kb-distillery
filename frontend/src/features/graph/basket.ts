import { create } from "zustand";
import { DRAFTS_KEY, isCompanion, normSlug, readDrafts, type DraftStore, type ScopeDraft, type ScopeRow } from "@/features/scopes/logic";

/**
 * The basket is the scope draft the Scopes screen reads: the same localStorage key and shape
 * (`{active, drafts: {[key]: {slug, title, isNew, rows}}}`, key = slug), so "Make scope" is only a link
 * to `/scopes?draft=<key>`. The functions here are pure; `useBasket` persists them.
 */
export interface BasketTarget {
  slug: string;
  title: string;
  isNew: boolean;
}

export const UNTITLED: BasketTarget = { slug: "scope-untitled-scope", title: "Untitled scope", isNew: true };

/** "My topic" -> a new-scope target; empty when the title has no usable characters. */
export function newTarget(title: string): BasketTarget | null {
  const slug = normSlug(title);
  return slug ? { slug, title: title.trim(), isNew: true } : null;
}

export interface AddResult {
  store: DraftStore;
  added: number;
  key: string;
}

/** Add rows to the draft of `target` (created when missing) and make it the active one. Companions never join. */
export function addRows(store: DraftStore, target: BasketTarget, rows: readonly ScopeRow[]): AddResult {
  const drafts = { ...store.drafts };
  const cur = drafts[target.slug];
  const draft: ScopeDraft = cur
    ? { ...cur, rows: [...cur.rows] }
    : { slug: target.slug, title: target.title, isNew: target.isNew, rows: [] };
  const have = new Set(draft.rows.map((r) => r.path));
  let added = 0;
  for (const r of rows) {
    if (!r.path || have.has(r.path) || isCompanion(r.disposition)) continue;
    have.add(r.path);
    draft.rows.push(r);
    added += 1;
  }
  drafts[target.slug] = draft;
  return { store: { active: target.slug, drafts }, added, key: target.slug };
}

export function removePath(store: DraftStore, path: string): DraftStore {
  const d = store.drafts[store.active];
  if (!d) return store;
  return { ...store, drafts: { ...store.drafts, [store.active]: { ...d, rows: d.rows.filter((r) => r.path !== path) } } };
}

export function discard(store: DraftStore): DraftStore {
  if (!store.active) return store;
  const drafts = { ...store.drafts };
  delete drafts[store.active];
  return { active: "", drafts };
}

export const activeDraft = (store: DraftStore): ScopeDraft | null => store.drafts[store.active] ?? null;

/** Rows grouped by raw format, in first-seen order. */
export function byFormat(rows: readonly ScopeRow[]): [string, ScopeRow[]][] {
  const groups = new Map<string, ScopeRow[]>();
  for (const r of rows) {
    const k = r.format || "other";
    (groups.get(k) ?? groups.set(k, []).get(k))?.push(r);
  }
  return [...groups];
}

function write(store: DraftStore): void {
  try {
    localStorage.setItem(DRAFTS_KEY, JSON.stringify(store));
  } catch {
    /* storage unavailable: the draft just lives for this visit */
  }
}

interface BasketState {
  store: DraftStore;
  /** Re-read the saved drafts (another tab, or the Scopes screen, changed them). */
  reload: () => void;
  add: (target: BasketTarget, rows: readonly ScopeRow[]) => AddResult;
  remove: (path: string) => void;
  discard: () => void;
}

export const useBasket = create<BasketState>((set, get) => ({
  store: readDrafts(),
  reload: () => set({ store: readDrafts() }),
  add: (target, rows) => {
    const res = addRows(get().store, target, rows);
    write(res.store);
    set({ store: res.store });
    return res;
  },
  remove: (path) => {
    const next = removePath(get().store, path);
    write(next);
    set({ store: next });
  },
  discard: () => {
    const next = discard(get().store);
    write(next);
    set({ store: next });
  },
}));

if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === DRAFTS_KEY || e.key === null) useBasket.getState().reload();
  });
}
