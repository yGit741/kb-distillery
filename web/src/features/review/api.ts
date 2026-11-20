import type { Finding, Hunk, Proposal } from "@/api";

/** One card of the deck (GET /api/review/deck, src/kb_distillery/proposals/review.py `deck`): one hunk of an open proposal. */
export interface Card {
  /** `<proposal id>:<hunk id>`: hunk ids are content-based, so a decision keyed by it survives a reload */
  id: string;
  proposal_id: string;
  hunk: Hunk;
  klass: string;
  tier: "auto_apply" | "review" | "explicit";
  page_title: string;
  context_before: string;
  context_after: string;
  decision: { decision: string; suggested?: boolean } | null;
  findings: Finding[];
  stale: boolean;
  /** `source:<raw path>` for an ingest, else `proposal:<id>` */
  group: string;
  producer: string;
  source: string;
  updated: string;
  /** the blast radius: pages linking here, linked from here, and links this change adds or removes */
  reach?: Reach;
}

export type ReachRel = "added" | "removed" | "in" | "out";
export interface ReachPage {
  slug: string;
  title: string;
  /** the page\'s OKF type (the mark it is drawn with) */
  type?: string;
  rel: ReachRel;
  exists: boolean;
}
export interface Reach {
  /** every connected page; `pages` is capped */
  total: number;
  pages: ReachPage[];
}

/** Context sent with a sentence: passages marked on the card and pages picked in the graph. */
export interface EditContext {
  marks: string[];
  pages: string[];
}

export interface DeckProposal {
  id: string;
  title: string;
  producer: string;
  instruction: string;
  source: string;
  stale: boolean;
  stale_pages: string[];
  updated: string;
  hunks: number;
  group: string;
}

export interface Deck {
  cards: Card[];
  proposals: DeckProposal[];
}

export type Choice = "accept" | "reject";

export interface ApplyOutcome {
  applied: { id: string; title: string; commit: string; pages: string[]; kb_version?: string | null }[];
  rejected: string[];
  waiting: { id: string; title: string; undecided: number }[];
  failed: { id: string; status: number; message: string; stale?: string[]; blocking?: Finding[] }[];
}

export interface Rewrite {
  proposal: Proposal;
  reply: string;
  hunk_id: string | null;
  others_changed: string[];
  unchanged: boolean;
}

export interface SplitResult {
  proposal: Proposal;
  reply: string;
  cuts: number[];
  titles: string[];
}

export class ReviewError extends Error {
  constructor(message: string, readonly status = 0) {
    super(message);
  }
}

type F = typeof fetch;

async function call<T>(f: F, path: string, body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await f(path, {
      method: body === undefined ? "GET" : "POST",
      headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch (e) {
    throw new ReviewError(`Could not reach the app: ${e instanceof Error ? e.message : String(e)}`);
  }
  const data = (await r.json().catch(() => ({}))) as { detail?: unknown };
  if (!r.ok) throw new ReviewError(typeof data.detail === "string" ? data.detail : `${path} answered ${r.status}`, r.status);
  return data as T;
}

export const reviewApi = (f: F = (...a) => fetch(...a)) => ({
  deck: () => call<Deck>(f, "/api/review/deck"),
  apply: (items: { proposal_id: string; decisions: { hunk_id: string; decision: Choice }[] }[]) =>
    call<ApplyOutcome>(f, "/api/review/apply", { items }),
  rewrite: (proposalId: string, hunkId: string, instruction: string, context: EditContext = { marks: [], pages: [] }) =>
    call<Rewrite>(f, `/api/review/${encodeURIComponent(proposalId)}/hunks/${encodeURIComponent(hunkId)}/rewrite`, { instruction, ...context }),
  revert: (proposalId: string) => call<Proposal>(f, `/api/review/${encodeURIComponent(proposalId)}/revert`, {}),
  split: (slug: string, hint?: string) => call<SplitResult>(f, "/api/review/split", { slug, hint: hint || null }),
  merge: (slugs: string[], survivor: string) => call<Proposal>(f, "/api/proposals/restructure/merge", { slugs, survivor }),
  mentions: async (q: string) => (await call<{ pages: { slug: string; title: string }[] }>(f, `/api/pages/mentions?q=${encodeURIComponent(q)}`)).pages,
});

export type ReviewApi = ReturnType<typeof reviewApi>;
