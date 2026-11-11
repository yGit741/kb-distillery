/**
 * The edit preview's view model: one queued item (a source, a flag, a chat edit) as the pages it touches and the
 * changes it proposes on each. Pure data and pure rules; the sheet renders it and the store holds the decisions.
 *
 * Review levels (the user approves everything, nothing applies by itself):
 *   - links and fixes: decided in bulk, per page or all at once;
 *   - additions (new text, nothing existing changes): quick, one row each, with Accept all;
 *   - needs a look: a rewrite of existing text, and every change on a protected page: decided one by one in the page.
 */

export type Decision = "accepted" | "rejected";

export interface Change {
  id: string;
  kind: "rewrite" | "addition";
  /** The sentence a rewrite replaces. */
  before?: string;
  after: string;
  /** Where in the source the claim comes from. */
  quote: string;
}

/** A page body in reading order: plain paragraphs and the changes that sit between them. */
export type Block = string | Change;

export interface SimilarPage {
  slug: string;
  title: string;
  why: string;
}

export interface PreviewPage {
  slug: string;
  title: string;
  type: string;
  areas: string[];
  isNew?: boolean;
  /** A protected page: every change on it is decided one by one, never in bulk. */
  protected?: boolean;
  body: Block[];
  links: number;
  fixes: number;
  similar: SimilarPage[];
}

/** A question with one picked answer: a merge or split choice, or where a left-out claim should go. */
export interface Choice {
  id: string;
  title: string;
  why: string;
  options: string[];
  picked: number;
}

export interface PreviewItem {
  id: string;
  title: string;
  pages: PreviewPage[];
  /** Asked once, before the pages: merge and split choices that shape the rest. */
  before: Choice[];
  /** Claims from the source that landed on no page. */
  leftOut: Choice[];
}

export interface QueueEntry {
  id: string;
  title: string;
  note: string;
  protected?: boolean;
}

export interface Decisions {
  /** change id -> decision */
  changes: Record<string, Decision>;
  /** page slug -> decision on that page's links and fixes */
  bulk: Record<string, Decision>;
  /** choice id -> picked option */
  choices: Record<string, number>;
}

export const NO_DECISIONS: Decisions = { changes: {}, bulk: {}, choices: {} };

export interface Row {
  page: PreviewPage;
  change: Change;
}

export const isChange = (b: Block): b is Change => typeof b !== "string";
export const changesOf = (p: PreviewPage): Change[] => p.body.filter(isChange);
export const bulkCount = (p: PreviewPage): number => p.links + p.fixes;
export const rowsOf = (item: PreviewItem): Row[] => item.pages.flatMap((page) => changesOf(page).map((change) => ({ page, change })));

/** A change that is decided in the page view, never from a list. */
export const needsLook = (r: Row): boolean => r.change.kind === "rewrite" || !!r.page.protected;

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "2 links", "1 link, 1 fix": what a page's bulk row carries. */
export function bulkLabel(p: Pick<PreviewPage, "links" | "fixes">): string {
  return [p.links ? plural(p.links, "link") : "", p.fixes ? plural(p.fixes, "fix", "fixes") : ""].filter(Boolean).join(", ");
}

/** "1 rewrite, 1 addition, 1 link" under a page title. */
export function pageSummary(p: PreviewPage): string {
  const ch = changesOf(p);
  const rw = ch.filter((c) => c.kind === "rewrite").length;
  const add = ch.length - rw;
  return [rw ? plural(rw, "rewrite") : "", add ? plural(add, "addition") : "", bulkLabel(p)].filter(Boolean).join(", ");
}

export interface Groups {
  /** Rewrites and everything on a protected page, in page order. */
  look: Row[];
  /** Protected pages whose links and fixes also wait for a decision in the page. */
  lookBulk: PreviewPage[];
  additions: Row[];
  /** Unprotected pages with links or fixes: one Accept all covers them. */
  bulk: PreviewPage[];
}

export function groupsOf(item: PreviewItem): Groups {
  const rows = rowsOf(item);
  const withBulk = item.pages.filter((p) => bulkCount(p) > 0);
  return {
    look: rows.filter(needsLook),
    lookBulk: withBulk.filter((p) => p.protected),
    additions: rows.filter((r) => !needsLook(r)),
    bulk: withBulk.filter((p) => !p.protected),
  };
}

export interface Open {
  look: number;
  additions: number;
  /** links and fixes still undecided, counted one by one */
  bulk: number;
  total: number;
}

export function openOf(item: PreviewItem, d: Decisions): Open {
  const g = groupsOf(item);
  const undecided = (rows: Row[]) => rows.filter((r) => !d.changes[r.change.id]).length;
  const bulkOpen = (pages: PreviewPage[]) => pages.filter((p) => !d.bulk[p.slug]).reduce((n, p) => n + bulkCount(p), 0);
  const look = undecided(g.look) + bulkOpen(g.lookBulk);
  const additions = undecided(g.additions);
  const bulk = bulkOpen(g.bulk);
  return { look, additions, bulk, total: look + additions + bulk };
}

/** Undecided changes, links and fixes on one page, one by one: a protected page moves on only at zero. */
export function openOnPage(p: PreviewPage, d: Decisions): number {
  return changesOf(p).filter((c) => !d.changes[c.id]).length + (d.bulk[p.slug] ? 0 : bulkCount(p));
}

export const pageDone = (p: PreviewPage, d: Decisions): boolean => openOnPage(p, d) === 0;

/** What Apply would write: accepted changes, links and fixes, counted one by one, and the pages they land on. */
export function applyCount(item: PreviewItem, d: Decisions): { changes: number; pages: number } {
  let changes = 0;
  let pages = 0;
  for (const p of item.pages) {
    const n = changesOf(p).filter((c) => d.changes[c.id] === "accepted").length + (d.bulk[p.slug] === "accepted" ? bulkCount(p) : 0);
    changes += n;
    if (n) pages += 1;
  }
  return { changes, pages };
}

/** Accept every still-open addition (never a rewrite, never a protected page). */
export function acceptAdditions(item: PreviewItem, d: Decisions): Decisions {
  const changes = { ...d.changes };
  for (const r of groupsOf(item).additions) changes[r.change.id] ??= "accepted";
  return { ...d, changes };
}

/** Accept the links and fixes of every unprotected page that is still open. */
export function acceptBulk(item: PreviewItem, d: Decisions): Decisions {
  const bulk = { ...d.bulk };
  for (const p of groupsOf(item).bulk) bulk[p.slug] ??= "accepted";
  return { ...d, bulk };
}

/** Accept what is still open on one page. Refused on a protected page: those are decided one by one. */
export function acceptRestOfPage(p: PreviewPage, d: Decisions): Decisions {
  if (p.protected) return d;
  const changes = { ...d.changes };
  for (const c of changesOf(p)) changes[c.id] ??= "accepted";
  const bulk = bulkCount(p) > 0 ? { ...d.bulk, [p.slug]: d.bulk[p.slug] ?? ("accepted" as const) } : d.bulk;
  return { ...d, changes, bulk };
}

/** The pages the page view steps through with < and >: the ones that carry something to look at. */
export function lookPages(item: PreviewItem): PreviewPage[] {
  const g = groupsOf(item);
  const slugs = new Set([...g.look.map((r) => r.page.slug), ...g.lookBulk.map((p) => p.slug)]);
  return item.pages.filter((p) => slugs.has(p.slug));
}
