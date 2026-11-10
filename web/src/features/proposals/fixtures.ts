import type { Proposal, ProposalRender } from "@/api";

/** A fixed proposal on one page: two prose edits (one adds a link), a frontmatter key, one warning. */
export function proposalFixture(over: Partial<Proposal> = {}): Proposal {
  const hunks: Proposal["hunks"] = [
    {
      id: "h-soften", op_id: "op1", op: "edit_page", slug: "tensor-rank", kind: "prose", klass: "claims", at: 2, span: 1,
      before: "Rank always determines the cost.\n\n", after: "Rank often determines the cost.\n\n",
      tokens: [["equal", "Rank "], ["delete", "always"], ["insert", "often"], ["equal", " determines the cost.\n\n"]],
      reason: "the claim is too strong", sources: ["paper-x"], links_added: [], links_removed: [],
    },
    {
      id: "h-link", op_id: "op1", op: "edit_page", slug: "tensor-rank", kind: "structure", klass: "links", at: 4, span: 1,
      before: "See the survey.\n", after: "See the survey and [Matrix rank](matrix-rank.md).\n",
      tokens: [["equal", "See the survey"], ["insert", " and [Matrix rank](matrix-rank.md)"], ["equal", ".\n"]],
      reason: "", sources: [], links_added: ["matrix-rank"], links_removed: [],
    },
    {
      id: "h-fm", op_id: "op2", op: "set_frontmatter", slug: "tensor-rank", kind: "structure", klass: "structure", at: 0, span: 0,
      before: "", after: "maturity: draft", tokens: [["insert", "maturity: draft"]],
      reason: "", sources: [], links_added: [], links_removed: [],
    },
  ];
  return {
    id: "p1", title: "Soften the rank claim", status: "open", stale: false, stale_pages: [],
    producer: { kind: "chat", instruction: "soften this, check against paper-x", context: {} },
    created: "2026-11-08T20:00:00+00:00", updated: "2026-11-08T20:00:00+00:00",
    base: { "tensor-rank": "abc" }, current: 0, revision: 1,
    revisions: [{ n: 1, created: "2026-11-08T20:00:00+00:00", note: "", ops: [], hunks, checks: [] }],
    hunks, decisions: {},
    checks: { tier1: [{ severity: "warning", code: "length", message: "the page is long", slug: "tensor-rank", hunk_id: null, source: "tier1" }], tier2: [] },
    counts: { hunks: 3, accepted: 0, rejected: 0, corrected: 0 },
    check_counts: { errors: 0, warnings: 1, blocking: 0 },
    ...over,
  } as Proposal;
}

export const renderFixture: ProposalRender = {
  id: "p1", revision: 1, stale: false,
  pages: [{
    slug: "tensor-rank", exists: true, text: "", my_notes: "",
    blocks: [
      { index: 0, kind: "fm", text: "---\ntype: idea\n---\n" },
      { index: 1, kind: "heading", text: "# Tensor rank\n\n" },
      { index: 2, kind: "prose", text: "Rank always determines the cost.\n\n" },
      { index: 3, kind: "prose", text: "An unchanged paragraph in between.\n\n" },
      { index: 4, kind: "prose", text: "See the survey.\n" },
    ],
    hunks: [],
  }],
} as unknown as ProposalRender;

import type { FeedItem, ProposalGroup, ProposalList, ProposalSummary } from "@/api";

export function summaryFixture(over: Partial<ProposalSummary> = {}): ProposalSummary {
  return {
    id: "p1", title: "Soften the rank claim", status: "open", producer: { kind: "chat" },
    created: "2026-11-08T20:00:00+00:00", updated: "2026-11-08T20:00:00+00:00", pages: ["tensor-rank"],
    counts: { hunks: 1, accepted: 0, rejected: 0, corrected: 0 }, checks: { errors: 0, warnings: 0, blocking: 0 },
    classes: { claims: 1 }, tiers: { auto_apply: 0, review: 1, explicit: 0 }, stale_pages: [], top_class: "claims",
    ...over,
  } as ProposalSummary;
}

const CLASS_RANK = ["claims", "structure", "new_page", "links", "format", "typos"];

/** What GET /api/proposals?group= answers for these rows (the server's grouping rules, small). */
export function inboxFixture(rows: ProposalSummary[], group?: string): ProposalList {
  const buckets = new Map<string, ProposalSummary[]>();
  for (const p of rows) for (const k of group === "page" ? p.pages : group === "class" ? [p.top_class] : []) buckets.set(k, [...(buckets.get(k) ?? []), p]);
  const keys = [...buckets.keys()].sort((a, b) => (group === "class" ? CLASS_RANK.indexOf(a) - CLASS_RANK.indexOf(b) : a.localeCompare(b)));
  const groups: ProposalGroup[] = keys.map((key) => ({ key, label: key, count: buckets.get(key)!.length, proposals: buckets.get(key)! }));
  return { proposals: rows, groups } as ProposalList;
}

export const inboxRows: ProposalSummary[] = [
  summaryFixture(),
  summaryFixture({ id: "p2", title: "Fix twenty link targets", pages: ["matrix-rank", "tensor-rank"], classes: { links: 20 }, tiers: { auto_apply: 20, review: 0, explicit: 0 }, top_class: "links", counts: { hunks: 20, accepted: 20, rejected: 0, corrected: 0 } }),
  summaryFixture({ id: "p3", title: "Add a new survey page", pages: ["survey"], classes: { new_page: 1, typos: 2 }, tiers: { auto_apply: 2, review: 1, explicit: 0 }, top_class: "new_page" }),
  summaryFixture({ id: "p4", title: "Retarget a link", status: "stale", pages: ["matrix-rank"], classes: { links: 1 }, tiers: { auto_apply: 1, review: 0, explicit: 0 }, top_class: "links", stale_pages: ["matrix-rank"] }),
];

export const feedItems: FeedItem[] = [
  { id: "f1", title: "Fix a typo", status: "applied", pages: ["tensor-rank"], hunks: 1, classes: ["typos"], applied_at: "2026-11-09T02:00:00+00:00", commit: "abc1234def", auto: true, undoable: true, blocked_by: [] },
  { id: "f2", title: "Tidy links", status: "applied", pages: ["matrix-rank"], hunks: 3, classes: ["links"], applied_at: "2026-11-09T01:00:00+00:00", commit: "bcd2345efa", auto: true, undoable: false, blocked_by: ["matrix-rank"] },
  { id: "f3", title: "Old format fix", status: "undone", pages: ["survey"], hunks: 1, classes: ["format"], applied_at: "2026-11-08T01:00:00+00:00", commit: null, auto: true, undoable: false, blocked_by: [], undone_at: "2026-11-08T03:00:00+00:00" },
];
