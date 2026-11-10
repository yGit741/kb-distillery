import type { Decision, Finding, Hunk, Proposal, RenderPage } from "@/api";

/** Where a hunk is reviewed: in the page text (`flow`) or as one line in the Structure strip. */
export type Placement = "flow" | "structure";

/**
 * Placement follows the op and the block, not `hunk.kind`: the core marks a paragraph edit that adds a link as
 * `structure`, but the owner still reads it as prose in the page. Frontmatter, link rewrites, new pages,
 * tombstones and moves go to the strip.
 */
export function placement(h: Hunk, page?: RenderPage): Placement {
  if (h.op !== "edit_page") return "structure";
  const blocks = page?.blocks ?? [];
  const first = blocks[h.at];
  if (h.span > 0 && first?.kind === "fm") return "structure";
  if (h.span === 0 && /^---\n/.test(h.after)) return "structure";
  return "flow";
}

/** The visual kind of a change, one ramp: insert (only new text), delete (only removed), modified (both). */
export type ChangeKind = "insert" | "delete" | "modified";
export const changeKind = (h: Hunk): ChangeKind => (!h.before.trim() ? "insert" : !h.after.trim() ? "delete" : "modified");
export const CHANGE_LABEL: Record<ChangeKind, string> = { insert: "added", delete: "removed", modified: "changed" };

/** One segment of a page as the review shows it: a run of unchanged blocks, or a hunk in place. */
export type Segment = { kind: "same"; blocks: { index: number; text: string }[] } | { kind: "hunk"; hunk: Hunk };

/** The page body cut into unchanged runs and flow hunks, in reading order (frontmatter left out). */
export function segments(page: RenderPage | undefined, hunks: Hunk[]): Segment[] {
  const flow = hunks.filter((h) => placement(h, page) === "flow").sort((a, b) => a.at - b.at || a.span - b.span);
  const blocks = (page?.blocks ?? []).filter((b) => b.kind !== "fm");
  if (!blocks.length) return flow.map((hunk) => ({ kind: "hunk", hunk }));
  const covered = new Set<number>();
  for (const h of flow) for (let i = h.at; i < h.at + h.span; i++) covered.add(i);
  const out: Segment[] = [];
  const pushSame = (b: { index: number; text: string }) => {
    const last = out[out.length - 1];
    if (last?.kind === "same") last.blocks.push(b);
    else out.push({ kind: "same", blocks: [b] });
  };
  const queue = [...flow];
  for (const b of blocks) {
    while (queue.length && queue[0]!.at <= b.index) out.push({ kind: "hunk", hunk: queue.shift()! });
    if (!covered.has(b.index)) pushSame({ index: b.index, text: b.text });
  }
  for (const hunk of queue) out.push({ kind: "hunk", hunk });
  return out;
}

/** Hunks in the order j/k walks them: the Structure strip first, then each page's text top to bottom. */
export function reviewOrder(hunks: Hunk[], pages: RenderPage[]): Hunk[] {
  const pageOf = (h: Hunk) => pages.find((p) => p.slug === h.slug);
  const strip = hunks.filter((h) => placement(h, pageOf(h)) === "structure");
  const flow: Hunk[] = [];
  const slugs = [...new Set([...pages.map((p) => p.slug), ...hunks.map((h) => h.slug)])];
  for (const s of slugs) {
    const page = pages.find((p) => p.slug === s);
    for (const seg of segments(page, hunks.filter((h) => h.slug === s))) if (seg.kind === "hunk") flow.push(seg.hunk);
  }
  return [...strip, ...flow];
}

export const decisionOf = (p: Proposal, id: string): Decision | undefined => p.decisions[id]?.decision as Decision | undefined;

/** Error findings that still block apply (the core's rule): on no hunk, or on a hunk that is not rejected. */
export function blockingFindings(findings: Finding[], p: Proposal): Finding[] {
  return findings.filter((f) => f.severity === "error" && !(f.hunk_id && decisionOf(p, f.hunk_id) === "reject"));
}

/** Why Apply is off, in one short sentence, or null when it can run. */
export function applyBlocker(p: Proposal, findings: Finding[], hunks: Hunk[]): string | null {
  if (p.status === "applied") return "This proposal is already applied.";
  if (p.status === "rejected") return "This proposal was rejected.";
  if (p.stale) return "The page changed since this proposal was made. Rebase it first.";
  const blocking = blockingFindings(findings, p);
  if (blocking.length) {
    const h = hunks.find((x) => x.id === blocking[0]!.hunk_id);
    return h ? `A check fails on the change "${short(h)}": reject it to apply the rest.` : "A check fails on the page as a whole.";
  }
  if (!p.counts.accepted) return "Accept at least one change.";
  return null;
}

/** A few words that name a hunk. */
export function short(h: Hunk, n = 4): string {
  const words = readable(h.after.trim() || h.before.trim()).split(/\s+/).filter(Boolean);
  return words.slice(0, n).join(" ") + (words.length > n ? " ..." : "");
}

/** Text as a reader sees it: page links reduced to their titles, heading marks and emphasis marks dropped. */
export function readable(text: string): string {
  return text
    .replace(/(?<!!)\[((?:[^[\]\\\n]|\\.)*)\]\(([^()<>\s/:#]+?)\.md(?:#[^()\s]*)?\)/g, "$1")
    .replace(/^#{1,6}[ \t]+/gm, "")
    .replace(/\*\*|__/g, "");
}

/** One line for a structure hunk: what it does, in words. */
export function structureLine(h: Hunk): { what: string; detail: string } {
  if (h.op === "set_frontmatter") {
    const [key, ...rest] = h.after.split(":");
    const old = h.before ? h.before.split(":").slice(1).join(":").trim() : "";
    return { what: `Set ${(key ?? "").trim()}`, detail: old ? `${old} -> ${rest.join(":").trim()}` : rest.join(":").trim() };
  }
  if (h.op === "create_page") return { what: "New page", detail: h.slug };
  if (h.op === "rewrite_link") return { what: "Rewrite link", detail: readable(h.after).trim() };
  if (h.op === "tombstone_page") return { what: "Retire page", detail: h.after.replace(/^tombstone\s+/, "") };
  if (h.op === "move_block") return { what: "Move block", detail: h.after.replace(/^move block\s+/, "") };
  return { what: "Frontmatter", detail: `${h.links_added.length + h.links_removed.length ? "links " : ""}${readable(h.after).trim().split("\n").length} lines` };
}

/** Hunk classes in the order the owner should read them: what changes a claim first, typos last. */
export const CLASS_ORDER = ["claims", "structure", "new_page", "tombstone", "split", "merge", "rename", "links", "format", "typos"] as const;
export const CLASS_LABEL: Record<string, string> = {
  claims: "Claims", structure: "Structure", new_page: "New pages", tombstone: "Retired pages", split: "Splits", merge: "Merges",
  rename: "Renames", links: "Links", format: "Formatting", typos: "Typos",
};
export const CLASS_HINT: Record<string, string> = {
  claims: "Wording that changes what a page says. Read these first.",
  structure: "Headings, frontmatter and link rewrites.",
  new_page: "Pages the agent wants to add.",
  tombstone: "Pages the agent wants to retire.",
  links: "Links added or retargeted; the words stay the same.",
  format: "Spacing and layout only.",
  typos: "One misspelled word at a time.",
};
export const classLabel = (k: string) => CLASS_LABEL[k] ?? k.replace(/_/g, " ");

/** The strictest trust tier a proposal touches, as the row's one mark. */
export function tierMark(tiers: Record<string, number>): { id: "explicit" | "review" | "auto_apply"; label: string; hint: string } {
  if (tiers.explicit) return { id: "explicit", label: "explicit", hint: "Has a change that is never applied without your explicit go-ahead." };
  if (tiers.review) return { id: "review", label: "review", hint: "Has a change you review before it applies." };
  return { id: "auto_apply", label: "auto-apply", hint: "Every change is of a kind the kb applies by itself." };
}

/** Rebase blocker sentence for a feed item that cannot be undone. */
export function undoBlocker(blockedBy: string[]): string {
  return blockedBy.length ? `Later changes touched ${blockedBy.join(", ")}; undo or resolve those first.` : "Its history cannot be read, so it cannot be undone safely.";
}
