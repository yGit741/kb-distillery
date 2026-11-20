import { describe, expect, it } from "vitest";
import { applyPlan, batchOf, buildItems, decide, emptyState, later, loadState, matchCommands, parseCommand, passCover, prune, saveState, undo, wordDiff } from "./model";
import { SAMPLE_DECK } from "./sample";

const { cards, proposals } = SAMPLE_DECK;
const ingest = cards.filter((c) => c.group.startsWith("source:"));
const chat = cards.find((c) => c.producer === "chat")!;
const lint = cards.filter((c) => c.producer === "lint");

describe("review deck", () => {
  it("opens a dropped source with its cover, new pages first, then claims, then one stack per low-risk class", () => {
    const items = buildItems(cards, emptyState());
    expect(items.map((i) => i.kind)).toEqual(["cover", "card", "card", "card", "stack"]);
    expect(items[1]!.kind === "card" && items[1]!.card.hunk.op).toBe("create_page");
    expect(items[3]!.id).toBe(chat.id);
    expect(items[4]!.kind === "stack" && items[4]!.cards).toHaveLength(lint.length);
  });

  it("passing the cover keeps its cards; Later on them moves on to the next change", () => {
    const passed = passCover(emptyState(), ingest[0]!.group);
    expect(buildItems(cards, passed)[0]!.kind).toBe("card");
    const s = later(emptyState(), ingest.map((c) => c.id));
    expect(buildItems(cards, s)[0]!.id).toBe(chat.id);
  });

  it("a decision leaves the deck and Undo brings it back, one step at a time", () => {
    let s = decide(emptyState(), [chat.id], "accept");
    s = decide(s, [chat.id], "reject");
    expect(buildItems(cards, s).some((i) => i.id === chat.id)).toBe(false);
    s = undo(s).state;
    expect(s.decisions[chat.id]).toBe("accept");
    s = undo(s).state;
    expect(chat.id in s.decisions).toBe(false);
    expect(undo(s).undone).toBeNull();
  });

  it("Apply writes a fully decided proposal, rejects an all-rejected one and waits on a half-decided one", () => {
    let s = decide(emptyState(), [chat.id], "accept");
    s = decide(s, lint.map((c) => c.id), "reject");
    s = decide(s, [ingest[0]!.id], "accept");
    const rows = applyPlan(cards, proposals, s);
    expect(Object.fromEntries(rows.map((r) => [r.proposal.id, r.outcome]))).toEqual({ "s-ingest": "wait", "s-chat": "apply", "s-lint": "reject" });
    const batch = batchOf(cards, s, rows);
    expect(batch.find((b) => b.proposal_id === "s-chat")!.decisions).toEqual([{ hunk_id: chat.hunk.id, decision: "accept" }]);
  });

  it("prune forgets cards that left the deck (applied, or rewritten into a new hunk)", () => {
    const s = later(decide(emptyState(), [chat.id], "accept"), [lint[0]!.id]);
    const p = prune(s, lint);
    expect(p.decisions).toEqual({});
    expect(p.later).toEqual([lint[0]!.id]);
    expect(p.history).toHaveLength(1);
  });

  it("remembers decisions per knowledge base", () => {
    saveState("kb-test", decide(emptyState(), [chat.id], "reject"));
    expect(loadState("kb-test").decisions).toEqual({ [chat.id]: "reject" });
    expect(loadState("kb-other").decisions).toEqual({});
  });
});

describe("edit line", () => {
  it("reads a sentence, /merge @page and /split [how]", () => {
    expect(parseCommand("  shorter please ")).toEqual({ kind: "instruction", text: "shorter please" });
    expect(parseCommand("/merge @hd-map")).toEqual({ kind: "merge", target: "hd-map" });
    expect(parseCommand("/split by sensor")).toEqual({ kind: "split", hint: "by sensor" });
    expect(parseCommand("/")).toEqual({ kind: "help" });
    expect(parseCommand("/frobnicate")).toEqual({ kind: "unknown", name: "/frobnicate" });
    expect(parseCommand("   ")).toBeNull();
  });

  it("the / menu narrows while the name is typed and closes at the first space", () => {
    expect(matchCommands("/").map((c) => c.name)).toEqual(["/merge", "/split"]);
    expect(matchCommands("/sp").map((c) => c.name)).toEqual(["/split"]);
    expect(matchCommands("/split ")).toEqual([]);
    expect(matchCommands("split")).toEqual([]);
  });

  it("word diff marks only what changed", () => {
    expect(wordDiff("latency is 80 ms", "latency is 120 ms")).toEqual([["equal", "latency is "], ["delete", "80"], ["insert", "120"], ["equal", " ms"]]);
    expect(wordDiff("same", "same")).toEqual([["equal", "same"]]);
  });
});
