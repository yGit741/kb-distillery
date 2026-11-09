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
