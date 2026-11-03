import type { CorpusRow, PageCard, ScopeRow } from "@/api/types";

/** Raw formats a scope may hold files from (raw/inbox is refused by the backend). */
export const FORMATS = [
  "printed-docs",
  "handwritten",
  "presentations",
  "llm-chats",
  "emails",
  "web-clips",
  "images",
  "videos",
] as const;

export const DRAFTS_KEY = "kb-scope-drafts";
/** The key drafts were saved under before it was made generic; read once, moved to DRAFTS_KEY, then removed. */
export const LEGACY_DRAFTS_KEY = "thesis-wiki-scope-drafts";
export const MAX_SHOWN = 600;
export const MAX_HITS = 30;

/** A scope draft as the graph basket writes it: `{active, drafts: {[key]: {slug, title, isNew, rows}}}`. */
export interface ScopeDraft {
  slug: string;
  title: string;
  isNew: boolean;
  rows: ScopeRow[];
}
export interface DraftStore {
  active: string;
  drafts: Record<string, ScopeDraft>;
}

const EMPTY: DraftStore = { active: "", drafts: {} };

type DraftReader = Pick<Storage, "getItem"> & Partial<Pick<Storage, "setItem" | "removeItem">>;

/** The stored drafts JSON: DRAFTS_KEY, else (once) the legacy key's value, moved to DRAFTS_KEY so no draft is lost. */
function storedDrafts(storage: DraftReader | null): string | null {
  const current = storage?.getItem(DRAFTS_KEY) ?? null;
  if (current !== null || !storage) return current;
  const legacy = storage.getItem(LEGACY_DRAFTS_KEY);
  if (legacy !== null && storage.setItem && storage.removeItem) {
    try {
      storage.setItem(DRAFTS_KEY, legacy);
      storage.removeItem(LEGACY_DRAFTS_KEY);
    } catch {
      /* storage full or read-only: keep reading the legacy key */
    }
  }
  return legacy;
}

export function readDrafts(storage: DraftReader | null = safeStorage()): DraftStore {
  try {
    const d = JSON.parse(storedDrafts(storage) ?? "null") as Partial<DraftStore> | null;
    return d && typeof d.drafts === "object" && d.drafts ? { active: d.active ?? "", drafts: d.drafts } : { ...EMPTY };
  } catch {
    return { ...EMPTY };
  }
}

export function dropDraft(key: string, storage: Pick<Storage, "getItem" | "setItem"> | null = safeStorage()): void {
  try {
    const s = readDrafts(storage);
    delete s.drafts[key];
    if (s.active === key) s.active = "";
    storage?.setItem(DRAFTS_KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable: nothing to drop */
  }
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

/** "My topic" -> "scope-my-topic"; empty stays empty. */
export function normSlug(raw: string): string {
  let s = raw
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (s && !s.startsWith("scope-")) s = "scope-" + s;
  return s;
}

/** File name below the format folder: raw/printed-docs/a/b.pdf -> a/b.pdf. */
export const nameOf = (path: string): string => path.split("/").slice(2).join("/");
export const formatOf = (path: string): string => path.split("/")[1] ?? "";

/** Rows of `extra` whose path is not in `rows` yet, de-duplicated. */
export function newRows(rows: readonly ScopeRow[], extra: readonly ScopeRow[]): ScopeRow[] {
  const have = new Set(rows.map((r) => r.path));
  const out: ScopeRow[] = [];
  for (const r of extra) {
    if (!have.has(r.path)) {
      have.add(r.path);
      out.push(r);
    }
  }
  return out;
}

export function corpusToRow(r: CorpusRow, format: string): ScopeRow {
  return {
    path: r.path,
    format,
    disposition: r.disposition ?? "queued",
    slug: r.slug ?? null,
    page_type: null,
    digestion: r.digestion,
    collection: r.collection,
    year: r.year ?? null,
  };
}

export interface RowFilter {
  undigested: boolean;
  formats: ReadonlySet<string>;
  collections: ReadonlySet<string>;
  text: string;
}
export const NO_FILTER: RowFilter = { undigested: false, formats: new Set(), collections: new Set(), text: "" };

export function filterRows(rows: readonly ScopeRow[], f: RowFilter): ScopeRow[] {
  const t = f.text.trim().toLowerCase();
  return rows.filter(
    (r) =>
      (!f.undigested || r.disposition === "queued") &&
      (!f.formats.size || f.formats.has(r.format)) &&
      (!f.collections.size || r.collection.some((c: string) => f.collections.has(c))) &&
      (!t || `${r.path} ${r.slug ?? ""} ${r.collection.join(" ")}`.toLowerCase().includes(t)),
  );
}

/** `source` is the manifest word for a digested raw file (schema 1.0); `partial` is a book with some chapters digested. */
export const isDigested = (r: Pick<ScopeRow, "disposition">): boolean =>
  r.disposition === "source" || r.disposition === "digested" || r.disposition === "partial";

/** asset / ink / dupe / sidecar rows ride with their parent file and are never scope members. */
export const isCompanion = (disposition: string | null | undefined): boolean => /^(asset|ink|dupe|sidecar)/.test(disposition ?? "");

export function stats(rows: readonly ScopeRow[]): { files: number; digested: number; pct: number } {
  const digested = rows.filter(isDigested).length;
  return { files: rows.length, digested, pct: rows.length ? Math.round((100 * digested) / rows.length) : 0 };
}

/** Stable text of what a Save would write; compared against the loaded baseline for "unsaved changes". */
export const snapshot = (title: string, why: string, rows: readonly ScopeRow[]): string =>
  JSON.stringify({ t: title.trim(), w: why.trim(), p: rows.map((r) => r.path).sort() });

export interface SaveCheck {
  error: string | null;
  slug: string;
}
export function checkSave(isNew: boolean, slugInput: string, title: string, why: string): SaveCheck {
  const slug = isNew ? normSlug(slugInput) : slugInput;
  if (!slug) return { slug, error: "Give the scope a slug." };
  if (!title.trim()) return { slug, error: "Give the scope a title." };
  if (!why.trim()) return { slug, error: "Why is required: say what question this scope serves." };
  return { slug, error: null };
}

/** Page hits of the picker: id or title contains every word of the query. */
export function matchPages(cards: readonly PageCard[], q: string, limit = 15): PageCard[] {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const out: PageCard[] = [];
  for (const c of cards) {
    const hay = `${c.id} ${c.title}`.toLowerCase();
    if (words.every((w) => hay.includes(w))) out.push(c);
    if (out.length >= limit) break;
  }
  return out;
}

/** Raw-file hits of the picker, outside the scope already. */
export function matchRaw(
  files: readonly ScopeRow[],
  have: ReadonlySet<string>,
  q: string,
  limit = MAX_HITS,
): ScopeRow[] {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const out: ScopeRow[] = [];
  for (const r of files) {
    if (have.has(r.path) || isCompanion(r.disposition)) continue;
    const hay = `${r.path} ${r.slug ?? ""} ${r.collection.join(" ")}`.toLowerCase();
    if (words.every((w) => hay.includes(w))) out.push(r);
    if (out.length >= limit) break;
  }
  return out;
}
