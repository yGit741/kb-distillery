import type { Card, Choice, DeckProposal } from "./api";

/** Low-risk change classes: collapsed into one stack card the owner can accept in one go (or open). */
export const STACK_CLASSES = ["links", "format", "typos"] as const;
export const isStackClass = (k: string): boolean => (STACK_CLASSES as readonly string[]).includes(k);
const CLASS_LABEL: Record<string, string> = {
  claims: "claim", structure: "structure", new_page: "new page", tombstone: "retired page", split: "split", merge: "merge",
  rename: "rename", links: "link fix", format: "format fix", typos: "typo fix",
};
export const classLabel = (k: string): string => CLASS_LABEL[k] ?? k.replace(/_/g, " ");
export const plural = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`;

export type Item =
  | { kind: "card"; id: string; card: Card }
  | { kind: "stack"; id: string; klass: string; cards: Card[] }
  | { kind: "cover"; id: string; group: string; source: string; newPages: number; changes: number; cards: Card[] };

/** What the person did, newest last; Undo walks it back (until Apply, nothing has reached the server). */
export type Step = { type: "decide"; ids: string[]; prev: Record<string, Choice | undefined> } | { type: "later"; ids: string[] } | { type: "cover"; group: string };

export interface DeckState {
  decisions: Record<string, Choice>;
  later: string[];
  covers: string[];
  /** stacks the person opened into single cards */
  opened: string[];
  history: Step[];
}

export const emptyState = (): DeckState => ({ decisions: {}, later: [], covers: [], opened: [], history: [] });

/** Decisions made elsewhere (the proposal screen) count; the server's suggested accepts do not decide a card. */
export function initialDecisions(cards: Card[]): Record<string, Choice> {
  const out: Record<string, Choice> = {};
  for (const c of cards) {
    const d = c.decision;
    if (d && !d.suggested && (d.decision === "accept" || d.decision === "reject")) out[c.id] = d.decision;
  }
  return out;
}

const fileName = (p: string) => p.split("/").pop() || p;
export const sourceLabel = (group: string): string => fileName(group.replace(/^source:/, ""));

/**
 * The deck in reading order: each dropped source opens with a cover card and its cards (new pages first), then the
 * other changes riskiest first (the server's order), then one stack per low-risk class. Decided, later and opened
 * stacks follow the state.
 */
export function buildItems(cards: Card[], s: DeckState): Item[] {
  const open = (c: Card) => !(c.id in s.decisions) && !s.later.includes(c.id);
  const groups = new Map<string, Card[]>();
  for (const c of cards) if (c.group.startsWith("source:")) groups.set(c.group, [...(groups.get(c.group) ?? []), c]);
  const items: Item[] = [];
  const newestFirst = [...groups.entries()].sort((a, b) => (b[1][0]!.updated > a[1][0]!.updated ? 1 : -1));
  for (const [group, mine] of newestFirst) {
    const left = mine.filter(open);
    if (!left.length) continue;
    if (!s.covers.includes(group))
      items.push({ kind: "cover", id: `cover:${group}`, group, source: mine[0]!.source, newPages: mine.filter((c) => c.hunk.op === "create_page").length, changes: mine.filter((c) => c.hunk.op !== "create_page").length, cards: left });
    const pages = left.filter((c) => c.hunk.op === "create_page");
    for (const c of [...pages, ...left.filter((c) => !pages.includes(c))]) items.push({ kind: "card", id: c.id, card: c });
  }
  const rest = cards.filter((c) => !c.group.startsWith("source:") && open(c));
  const stacks = new Map<string, Card[]>();
  for (const c of rest) {
    if (isStackClass(c.klass) && !s.opened.includes(c.klass)) stacks.set(c.klass, [...(stacks.get(c.klass) ?? []), c]);
    else items.push({ kind: "card", id: c.id, card: c });
  }
  for (const k of STACK_CLASSES) {
    const mine = stacks.get(k);
    if (!mine) continue;
    if (mine.length === 1) items.push({ kind: "card", id: mine[0]!.id, card: mine[0]! });
    else items.push({ kind: "stack", id: `stack:${k}`, klass: k, cards: mine });
  }
  return items;
}

export const itemCards = (i: Item): Card[] => (i.kind === "card" ? [i.card] : i.kind === "stack" ? i.cards : []);

export function decide(s: DeckState, ids: string[], d: Choice): DeckState {
  const prev: Record<string, Choice | undefined> = {};
  const decisions = { ...s.decisions };
  for (const id of ids) {
    prev[id] = decisions[id];
    decisions[id] = d;
  }
  return { ...s, decisions, later: s.later.filter((id) => !ids.includes(id)), history: [...s.history, { type: "decide", ids, prev }] };
}

export const later = (s: DeckState, ids: string[]): DeckState => ({ ...s, later: [...new Set([...s.later, ...ids])], history: [...s.history, { type: "later", ids }] });

export const passCover = (s: DeckState, group: string): DeckState => ({ ...s, covers: [...s.covers, group], history: [...s.history, { type: "cover", group }] });

export const openStack = (s: DeckState, klass: string): DeckState => ({ ...s, opened: [...new Set([...s.opened, klass])] });

/** The last step taken back; `undone` names what came back (for the live region). */
export function undo(s: DeckState): { state: DeckState; undone: Step | null } {
  const step = s.history[s.history.length - 1];
  if (!step) return { state: s, undone: null };
  const history = s.history.slice(0, -1);
  if (step.type === "decide") {
    const decisions = { ...s.decisions };
    for (const id of step.ids) {
      const p = step.prev[id];
      if (p) decisions[id] = p;
      else delete decisions[id];
    }
    return { state: { ...s, decisions, history }, undone: step };
  }
  if (step.type === "later") return { state: { ...s, later: s.later.filter((id) => !step.ids.includes(id)), history }, undone: step };
  return { state: { ...s, covers: s.covers.filter((g) => g !== step.group), history }, undone: step };
}

/** Back from the Later pile into the deck. */
export const reviewLater = (s: DeckState): DeckState => ({ ...s, later: [] });

/** Drop state for cards that left the deck (applied, rewritten into a new hunk id, rejected elsewhere). */
export function prune(s: DeckState, cards: Card[]): DeckState {
  const ids = new Set(cards.map((c) => c.id));
  const groups = new Set(cards.map((c) => c.group));
  const decisions = Object.fromEntries(Object.entries(s.decisions).filter(([id]) => ids.has(id)));
  return { ...s, decisions, later: s.later.filter((id) => ids.has(id)), covers: s.covers.filter((g) => groups.has(g)), history: s.history.filter((h) => h.type === "cover" || h.ids.every((id) => ids.has(id))) };
}

export interface PlanRow {
  proposal: DeckProposal;
  accepted: number;
  rejected: number;
  undecided: number;
  /** what Apply does with it: write the accepted cards, reject the whole proposal, or leave it for later */
  outcome: "apply" | "reject" | "wait";
}

/** What Apply would do, per proposal the person touched. */
export function applyPlan(cards: Card[], proposals: DeckProposal[], s: DeckState): PlanRow[] {
  const rows: PlanRow[] = [];
  for (const p of proposals) {
    const mine = cards.filter((c) => c.proposal_id === p.id);
    const accepted = mine.filter((c) => s.decisions[c.id] === "accept").length;
    const rejected = mine.filter((c) => s.decisions[c.id] === "reject").length;
    if (!accepted && !rejected) continue;
    const undecided = mine.length - accepted - rejected;
    rows.push({ proposal: p, accepted, rejected, undecided, outcome: undecided ? "wait" : accepted ? "apply" : "reject" });
  }
  return rows;
}

export const batchOf = (cards: Card[], s: DeckState, rows: PlanRow[]) =>
  rows.map((r) => ({
    proposal_id: r.proposal.id,
    decisions: cards.filter((c) => c.proposal_id === r.proposal.id && s.decisions[c.id]).map((c) => ({ hunk_id: c.hunk.id, decision: s.decisions[c.id]! })),
  }));

// --- the edit line ------------------------------------------------------------------------------------------------------
export type Command = { kind: "instruction"; text: string } | { kind: "merge"; target: string } | { kind: "split"; hint: string } | { kind: "help" } | { kind: "unknown"; name: string };

export const COMMANDS = [
  { name: "/merge", args: "@page", hint: "Merge another page into this one; its links are rewritten" },
  { name: "/split", args: "[how]", hint: "The model splits this page into focused pages" },
] as const;

export function parseCommand(raw: string): Command | null {
  const text = raw.trim();
  if (!text) return null;
  if (!text.startsWith("/")) return { kind: "instruction", text };
  const [name = "", ...rest] = text.split(/\s+/);
  const arg = rest.join(" ").trim();
  if (name === "/" || name === "/help") return { kind: "help" };
  if (name === "/merge") return { kind: "merge", target: arg.replace(/^@/, "") };
  if (name === "/split") return { kind: "split", hint: arg };
  return { kind: "unknown", name };
}

/** Commands whose name starts with what is typed (the `/` menu). */
export const matchCommands = (raw: string) => {
  const name = raw.trim().split(/\s+/)[0] ?? "";
  return raw.startsWith("/") && !/\s/.test(raw) ? COMMANDS.filter((c) => c.name.startsWith(name)) : [];
};

/** Word-level marks between two texts, as the server's hunk tokens ([op, text], op equal|insert|delete). */
export function wordDiff(a: string, b: string): string[][] {
  const split = (s: string) => s.match(/\s+|\w+|[^\w\s]/g) ?? [];
  const x = split(a);
  const y = split(b);
  if (x.length * y.length > 4_000_000) return [["delete", a], ["insert", b]];
  const n = x.length;
  const m = y.length;
  const lcs: Uint32Array[] = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) lcs[i]![j] = x[i] === y[j] ? lcs[i + 1]![j + 1]! + 1 : Math.max(lcs[i + 1]![j]!, lcs[i]![j + 1]!);
  const out: string[][] = [];
  const add = (op: string, t: string) => {
    const last = out[out.length - 1];
    if (last && last[0] === op) last[1] += t;
    else out.push([op, t]);
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) {
      add("equal", x[i]!);
      i++;
      j++;
    } else if (lcs[i + 1]![j]! >= lcs[i]![j + 1]!) add("delete", x[i++]!);
    else add("insert", y[j++]!);
  }
  while (i < n) add("delete", x[i++]!);
  while (j < m) add("insert", y[j++]!);
  return out;
}

// --- remembered per knowledge base -------------------------------------------------------------------------------------
const KEY = (kb: string) => `kb.review.${kb}`;

export function loadState(kb: string): DeckState {
  try {
    const raw = globalThis.localStorage?.getItem(KEY(kb));
    if (!raw) return emptyState();
    const v = JSON.parse(raw) as Partial<DeckState>;
    return { ...emptyState(), decisions: v.decisions ?? {}, later: v.later ?? [], covers: v.covers ?? [], opened: v.opened ?? [] };
  } catch {
    return emptyState();
  }
}

export function saveState(kb: string, s: DeckState): void {
  try {
    globalThis.localStorage?.setItem(KEY(kb), JSON.stringify({ decisions: s.decisions, later: s.later, covers: s.covers, opened: s.opened }));
  } catch {
    // storage blocked: the deck still works, it just forgets on reload
  }
}
