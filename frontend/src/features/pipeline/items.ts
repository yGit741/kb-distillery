/**
 * Pure logic of the pipeline screen: the snapshot's untyped records become typed items, files fold
 * into units (an email thread, a PDF with its ink overlay), and units are filtered, grouped and sorted.
 * Words: a unit moves Add (inbox) -> Catalog (filed with a record) -> Digest (depth easy/full/deep).
 */
import type { PipelineSnapshot } from "@/api/types";
import type { Depth } from "@/api/model";
import { DEPTHS } from "@/api/model";

export const STATUSES = ["inbox", "failed", "uncataloged", "undigested", "partial", "digested", "skipped"] as const;
export type Status = (typeof STATUSES)[number];
/** `cataloged` is a filter alias for every status after the Catalog step. */
export type StatusFilter = Status | "cataloged";
export const STATUS_FILTERS: readonly StatusFilter[] = [...STATUSES, "cataloged"];

export const STATUS_LABEL: Record<StatusFilter, string> = {
  inbox: "in inbox",
  failed: "failed",
  uncataloged: "not cataloged",
  undigested: "not digested",
  partial: "partial",
  digested: "digested",
  skipped: "skipped",
  cataloged: "cataloged",
};

export const STATUS_TIP: Record<StatusFilter, string> = {
  inbox: "In raw/inbox/, waiting to be cataloged.",
  failed: "Cataloging tried and stopped; the reason is shown on the file.",
  uncataloged: "Already in a raw/ format folder but never cataloged: no record, no collection, no note.",
  undigested: "Cataloged, no digest yet. This is the real backlog.",
  partial: "A book or notebook with only some page-range parts written up.",
  digested: "Has a wiki note from an easy, full or deep read.",
  skipped: "Deliberately not worth a note: a decision, not neglect.",
  cataloged: "Filed in its format folder with a record (collection, stub or course row).",
};

export const DEPTH_TIP: Record<Depth, string> = {
  listed: "Cataloged with a stub page, not read yet.",
  easy: "A skim of the abstract (~2-4k tokens).",
  full: "A proper read: method, results, key equations (~8-12k tokens).",
  deep: "A close, thesis-critical read with proofs and neighbours (~25-40k+ tokens).",
};

export const FORMAT_ORDER = ["inbox", "printed-docs", "handwritten", "presentations", "llm-chats", "emails", "web-clips", "images"];

export const VIEWS = ["list", "board", "timeline"] as const;
export type View = (typeof VIEWS)[number];
export const GROUPS = ["none", "format", "collection", "status", "depth"] as const;
export type Group = (typeof GROUPS)[number];

export interface PipelineItem {
  path: string;
  name: string;
  format: string;
  collections: string[];
  unit: string;
  companionOf: string;
  disposition: string;
  ingestion: string;
  digestion: string;
  depth: Depth | "";
  slug: string;
  ext: string;
  sizeKb: number;
  ageDays: number | null;
  lastOp: string;
  lastOpAt: string;
  sourceUrl: string;
  failure: string;
  next: string;
}

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => !!v && typeof v === "object" && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const rows = (v: unknown): Rec[] => (Array.isArray(v) ? v.filter(isRec) : []);

export function toItem(r: Rec): PipelineItem {
  const depth = str(r.depth);
  return {
    path: str(r.path),
    name: str(r.name) || str(r.path).split("/").pop() || "",
    format: str(r.kind),
    collections: strs(r.collections),
    unit: str(r.unit) || str(r.path),
    companionOf: str(r.companion_of),
    disposition: str(r.status),
    ingestion: str(r.ingestion),
    digestion: str(r.digestion),
    depth: depth === "easy" || depth === "full" || depth === "deep" ? depth : "",
    slug: str(r.slug),
    ext: str(r.ext).toLowerCase(),
    sizeKb: num(r.size_kb) ?? 0,
    ageDays: num(r.age_days),
    lastOp: str(r.last_op),
    lastOpAt: str(r.last_op_at),
    sourceUrl: str(r.url),
    failure: str(r.failure),
    next: str(r.next),
  };
}

export interface Unit {
  key: string;
  primary: PipelineItem;
  files: PipelineItem[];
  companions: PipelineItem[];
  isThread: boolean;
  name: string;
  format: string;
  collections: string[];
  status: Status;
  depth: Depth | "";
  /** In the corpus backlog (disposition queued): nothing has been done with it yet. */
  backlog: boolean;
  slug: string;
  sizeKb: number;
  ageDays: number | null;
  lastOp: string;
  lastOpAt: string;
  next: string;
  failure: string;
  search: string;
}

export function statusOf(f: PipelineItem): Status {
  if (f.ingestion === "inbox" || f.ingestion === "failed" || f.ingestion === "uncataloged") return f.ingestion;
  if (f.digestion === "digested") return "digested";
  if (f.digestion === "partial") return "partial";
  if (f.digestion === "skipped") return "skipped";
  return "undigested";
}

export function depthOf(f: PipelineItem): Depth | "" {
  if (f.depth) return f.depth;
  return statusOf(f) === "undigested" && f.slug ? "listed" : "";
}

export function inCatalog(s: Status): boolean {
  return s === "undigested" || s === "partial" || s === "digested" || s === "skipped";
}

export function buildUnits(items: PipelineItem[], titles: Record<string, string> = {}): Unit[] {
  const map = new Map<string, PipelineItem[]>();
  for (const it of items) {
    const list = map.get(it.unit);
    if (list) list.push(it);
    else map.set(it.unit, [it]);
  }
  const out: Unit[] = [];
  for (const [key, files] of map) {
    const primary = files.find((f) => !f.companionOf) ?? files[0]!;
    const companions = files.filter((f) => f !== primary);
    const collections = [...new Set(files.flatMap((f) => f.collections))];
    const ages = files.map((f) => f.ageDays).filter((a): a is number => a !== null);
    const last = files.reduce((m, f) => (f.lastOpAt > m.lastOpAt ? f : m), files[0]!);
    const isThread = primary.name === "thread.md";
    out.push({
      key,
      primary,
      files,
      companions,
      isThread,
      name: isThread ? key.split("/").pop() || key : primary.name,
      format: primary.format,
      collections,
      status: statusOf(primary),
      depth: depthOf(primary),
      backlog: primary.disposition === "queued",
      slug: primary.slug,
      sizeKb: files.reduce((n, f) => n + f.sizeKb, 0),
      ageDays: ages.length ? Math.min(...ages) : null,
      lastOp: last.lastOp,
      lastOpAt: last.lastOpAt,
      next: primary.next,
      failure: primary.failure,
      search: [...files.map((f) => `${f.path} ${f.slug}`), ...collections, ...collections.map((c) => titles[c] ?? "")]
        .join(" ")
        .toLowerCase(),
    });
  }
  return out;
}

export interface Failure { path: string; reason: string }
export interface Recent { ts: string; path: string; dest: string; collection: string }
export interface SnapshotData {
  units: Unit[];
  titles: Record<string, string>;
  failures: Failure[];
  recent: Recent[];
  generatedAt: string;
  queued: { units: number; mb: number };
}

export function parseSnapshot(snap: PipelineSnapshot): SnapshotData {
  const titles: Record<string, string> = {};
  if (isRec(snap.titles)) for (const [k, v] of Object.entries(snap.titles)) if (typeof v === "string") titles[k] = v;
  const items = rows(snap.items).map(toItem).filter((i) => i.path);
  const summary = isRec(snap.summary) ? snap.summary : {};
  return {
    units: buildUnits(items, titles),
    titles,
    failures: rows(snap.failures).map((r) => ({ path: str(r.path), reason: str(r.reason) })),
    recent: rows(snap.recent).map((r) => ({ ts: str(r.ts), path: str(r.path), dest: str(r.dest), collection: str(r.collection) })),
    generatedAt: str(snap.generated_at),
    queued: { units: num(summary.queued_units) ?? 0, mb: num(summary.queued_mb) ?? 0 },
  };
}

export interface Filters {
  q?: string;
  format?: string;
  collection?: string;
  status?: string;
  depth?: string;
  backlog?: boolean;
}

export function matchStatus(u: Unit, status: string | undefined): boolean {
  if (!status) return true;
  if (status === "cataloged") return inCatalog(u.status);
  return u.status === status;
}

export function filterUnits(units: Unit[], f: Filters): Unit[] {
  const q = (f.q ?? "").trim().toLowerCase();
  return units.filter(
    (u) =>
      (!f.format || u.format === f.format) &&
      matchStatus(u, f.status) &&
      (!f.depth || u.depth === f.depth) &&
      (!f.backlog || u.backlog) &&
      (!f.collection || (f.collection === "@none" ? !u.collections.length : u.collections.includes(f.collection))) &&
      (!q || u.search.includes(q)),
  );
}

const rank = (list: readonly string[], v: string) => {
  const i = list.indexOf(v);
  return i < 0 ? 99 : i;
};

export const groupKey = (u: Unit, g: Group): string => {
  switch (g) {
    case "format": return u.format;
    case "collection": return u.collections[0] ?? "";
    case "status": return u.status;
    case "depth": return u.depth || "not read";
    default: return "";
  }
};

export function groupLabel(k: string, g: Group, titles: Record<string, string>): string {
  if (g === "collection") return k ? titles[k] ?? k : "(no collection)";
  if (g === "status") return STATUS_LABEL[k as StatusFilter] ?? k;
  return k || "all";
}

export function compareGroups(g: Group, titles: Record<string, string>) {
  return (a: string, b: string): number => {
    if (g === "format") return rank(FORMAT_ORDER, a) - rank(FORMAT_ORDER, b) || a.localeCompare(b);
    if (g === "status") return rank(STATUSES, a) - rank(STATUSES, b);
    if (g === "depth") return rank(["deep", "full", "easy", "listed", "not read"], a) - rank(["deep", "full", "easy", "listed", "not read"], b);
    if (g === "collection") return (a ? 0 : 1) - (b ? 0 : 1) || groupLabel(a, g, titles).localeCompare(groupLabel(b, g, titles));
    return 0;
  };
}

export function groupUnits(units: Unit[], g: Group, titles: Record<string, string>): [string, Unit[]][] {
  const map = new Map<string, Unit[]>();
  for (const u of units) {
    const k = groupKey(u, g);
    const list = map.get(k);
    if (list) list.push(u);
    else map.set(k, [u]);
  }
  const cmp = compareGroups(g, titles);
  return [...map.entries()].sort((a, b) => cmp(a[0], b[0]));
}

/** Backlog first (most work left), then format, then name. */
export function sortUnits(units: Unit[]): Unit[] {
  return [...units].sort(
    (a, b) =>
      rank(STATUSES, a.status) - rank(STATUSES, b.status) ||
      rank(FORMAT_ORDER, a.format) - rank(FORMAT_ORDER, b.format) ||
      a.name.localeCompare(b.name),
  );
}

/** Timeline: months newest first by the last operation on each unit; units with no date go last. */
export function groupByMonth(units: Unit[]): [string, Unit[]][] {
  const sorted = [...units].sort((a, b) => b.lastOpAt.localeCompare(a.lastOpAt) || a.name.localeCompare(b.name));
  const map = new Map<string, Unit[]>();
  for (const u of sorted) {
    const k = /^\d{4}-\d{2}/.test(u.lastOpAt) ? u.lastOpAt.slice(0, 7) : "unknown";
    const list = map.get(k);
    if (list) list.push(u);
    else map.set(k, [u]);
  }
  return [...map.entries()];
}

export interface Counts {
  total: number;
  status: Record<Status, number>;
  cataloged: number;
  depth: Record<Depth, number>;
  backlog: number;
}

export function countUnits(units: Unit[]): Counts {
  const status = Object.fromEntries(STATUSES.map((s) => [s, 0])) as Record<Status, number>;
  const depth = Object.fromEntries(DEPTHS.map((d) => [d, 0])) as Record<Depth, number>;
  let backlog = 0;
  for (const u of units) {
    status[u.status] += 1;
    if (u.depth) depth[u.depth] += 1;
    if (u.backlog) backlog += 1;
  }
  const cataloged = status.undigested + status.partial + status.digested + status.skipped;
  return { total: units.length, status, cataloged, depth, backlog };
}

export function fmtSize(kb: number): string {
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${Math.round(kb)} KB`;
}

export function fmtAge(days: number | null): string {
  if (days === null) return "-";
  if (days < 1) return "today";
  if (days < 60) return `${Math.round(days)}d`;
  if (days < 730) return `${Math.round(days / 30)}mo`;
  return `${(days / 365).toFixed(1)}y`;
}

const enc = (path: string) => path.split("/").map(encodeURIComponent).join("/");
export const rawFileUrl = (path: string) => `/api/raw/${enc(path)}/file`;
export const rawThumbUrl = (path: string, w = 900) => `/api/raw/${enc(path)}/thumb?w=${w}`;

export const IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".webp"];
export const TEXT_EXTS = [".md", ".txt", ".html", ".json", ".eml"];
export type PreviewKind = "pdf" | "image" | "text" | "none";
export function previewKind(ext: string): PreviewKind {
  if (ext === ".pdf") return "pdf";
  if (IMAGE_EXTS.includes(ext)) return "image";
  if (TEXT_EXTS.includes(ext)) return "text";
  return "none";
}

/** Digest runs the easy skim on one cataloged file that has no digest yet. */
export function canDigest(u: Unit): boolean {
  return u.status === "undigested" && !!u.primary.path && previewKind(u.primary.ext) !== "none";
}

/** Relative links inside a raw clip (../images/x.jpg) point at other raw files: route them to the raw file endpoint. */
export function resolveRawUrl(href: string, baseDir: string): string {
  if (/^(?:[a-z][a-z0-9+.-]*:|\/|#)/i.test(href)) return href;
  const parts = baseDir.split("/").filter(Boolean);
  for (const seg of href.split("/")) {
    if (seg === "..") parts.pop();
    else if (seg && seg !== ".") parts.push(seg);
  }
  let path = parts.join("/");
  try { path = decodeURIComponent(path); } catch { /* keep as is */ }
  return path.startsWith("raw/") ? rawFileUrl(path) : href;
}
