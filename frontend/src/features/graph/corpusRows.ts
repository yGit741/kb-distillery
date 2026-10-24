import type { CorpusRow } from "@/api";
import type { ScopeRow } from "@/features/scopes/logic";
import { dispositionHead, isCompanionDisposition } from "./rawLayer";

/** One line of the drawer: a raw file, with the companions folded into it counted. */
export interface DrawerRow {
  path: string;
  format: string;
  disposition: string;
  slug: string | null;
  collection: string[];
  year: number | null;
  digestion: string;
  title: string;
  /** asset / ink / dupe files that belong to this one */
  companions: number;
}

export const ROW_CAP = 400;

export const formatOfPath = (path: string): string => path.split("/")[1] ?? "";
export const nameOfPath = (path: string): string => path.split("/").slice(2).join("/") || path;

/** The parent file of a companion row (`companion_of`, else the tail of `asset:raw/x.md`), or null. */
export function parentOf(r: { disposition?: string | null; companion_of?: string | null }): string | null {
  if (r.companion_of) return r.companion_of;
  const [head, ...rest] = (r.disposition ?? "").split(":");
  return rest.length && isCompanionDisposition(head) ? rest.join(":") : null;
}

/**
 * Companions (a web clip's figures, a reMarkable overlay, a superseded duplicate, an agent sidecar) ride
 * with their parent: they are not listed, they raise the parent's `companions` count. A companion whose
 * parent is not in the list (another format) is dropped too: it is never a file to digest or scope.
 */
export function foldCompanions(rows: readonly DrawerRow[], parents: ReadonlyMap<string, string | null>): DrawerRow[] {
  const count = new Map<string, number>();
  for (const r of rows) {
    const p = parents.get(r.path);
    if (p) count.set(p, (count.get(p) ?? 0) + 1);
  }
  return rows.filter((r) => !isCompanionDisposition(r.disposition) && !parents.get(r.path)).map((r) => ({ ...r, companions: count.get(r.path) ?? 0 }));
}

const base = (path: string, over: Partial<DrawerRow>): DrawerRow => ({
  path,
  format: formatOfPath(path),
  disposition: "queued",
  slug: null,
  collection: [],
  year: null,
  digestion: "",
  title: "",
  companions: 0,
  ...over,
});

/** A format's corpus table as drawer rows. */
export function fromCorpus(rows: readonly CorpusRow[], format: string): DrawerRow[] {
  const parents = new Map(rows.map((r) => [r.path, parentOf(r)] as const));
  return foldCompanions(
    rows.map((r) => base(r.path, { format, disposition: r.disposition ?? "queued", slug: r.slug ?? null, collection: r.collection, year: r.year ?? null, digestion: r.digestion, title: r.title })),
    parents,
  );
}

/** The raw files behind a selection (scope-resolve rows; companions already left out by the backend). */
export function fromScopeRows(rows: readonly ScopeRow[]): DrawerRow[] {
  const parents = new Map(rows.map((r) => [r.path, parentOf(r)] as const));
  return foldCompanions(
    rows.map((r) => base(r.path, { format: r.format, disposition: r.disposition ?? "queued", slug: r.slug ?? null, collection: r.collection, year: r.year ?? null, digestion: r.digestion })),
    parents,
  );
}

/** Back to the scope-draft row shape (what the basket and the Scopes screen store). */
export const toScopeRow = (r: DrawerRow): ScopeRow => ({
  path: r.path,
  format: r.format,
  disposition: r.disposition,
  slug: r.slug,
  page_type: null,
  digestion: r.digestion,
  collection: r.collection,
  year: r.year,
});

/** Dispositions present, most common first (`source`, `queued`, `partial`, `skip`...). */
export function dispositionChips(rows: readonly DrawerRow[]): { id: string; n: number }[] {
  const n = new Map<string, number>();
  for (const r of rows) {
    const h = dispositionHead(r.disposition) || "queued";
    n.set(h, (n.get(h) ?? 0) + 1);
  }
  return [...n].map(([id, count]) => ({ id, n: count })).sort((a, b) => b.n - a.n || a.id.localeCompare(b.id));
}

export function filterRows(rows: readonly DrawerRow[], text: string, chips: ReadonlySet<string>): DrawerRow[] {
  const t = text.trim().toLowerCase();
  return rows.filter(
    (r) =>
      (!chips.size || chips.has(dispositionHead(r.disposition) || "queued")) &&
      (!t || `${r.path} ${r.title} ${r.slug ?? ""} ${r.collection.join(" ")} ${r.disposition}`.toLowerCase().includes(t)),
  );
}

export type SortKey = "name" | "disposition" | "slug" | "year";

export function sortRows(rows: readonly DrawerRow[], key: SortKey | null, dir: 1 | -1): DrawerRow[] {
  if (!key) return [...rows];
  const val = (r: DrawerRow): string | number | null =>
    key === "name" ? nameOfPath(r.path) : key === "disposition" ? r.disposition : key === "slug" ? r.slug : r.year;
  return [...rows].sort((a, b) => {
    const x = val(a);
    const y = val(b);
    if (x === y) return 0;
    if (x === null || x === "") return 1;
    if (y === null || y === "") return -1;
    return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * dir;
  });
}

export const isDigestedRow = (r: Pick<DrawerRow, "disposition">): boolean => ["source", "digested", "partial"].includes(dispositionHead(r.disposition));
export const canDigest = (r: Pick<DrawerRow, "disposition">): boolean => dispositionHead(r.disposition) === "queued";
