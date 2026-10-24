import { fmtUsd, tokenLine } from "./format";
import { isCustom, parsePrompts, pick, setEdit, systemFor } from "./prompts";
import { authPayload, authValue, backendLabel, effectiveBackend, parseStatus } from "./status";
import { applyEvent, canSave, dropLastTurn, historyOf, savableMessages, type Chat } from "./thread";
import { chatStatus } from "./fixtures";

const base = (): Chat => ({
  id: "c",
  session: null,
  messages: [
    { role: "user", content: "q" },
    { role: "assistant", content: "" },
  ],
});

describe("applyEvent", () => {
  it("accumulates deltas, tool steps by id, sources, session and usage", () => {
    let c = base();
    c = applyEvent(c, { type: "delta", text: "Hel" });
    c = applyEvent(c, { type: "delta", text: "lo" });
    c = applyEvent(c, { type: "tool", step: { name: "Read", summary: "read a", id: "1" } });
    c = applyEvent(c, { type: "tool", step: { name: "Read", summary: "read a", id: "1", error: true } });
    c = applyEvent(c, { type: "sources", hits: [{ slug: "a", score: 1, summary: "", in_context: false }], fresh: ["a"] });
    c = applyEvent(c, { type: "session", id: "s9" });
    c = applyEvent(c, { type: "usage", usage: { output_tokens: 5 } });
    const bot = c.messages[1]!;
    expect(bot.content).toBe("Hello");
    expect(bot.trace).toEqual([{ name: "Read", summary: "read a", id: "1", error: true }]);
    expect(bot.hits).toHaveLength(1);
    expect(c.messages[0]!.sources).toEqual(["a"]);
    expect(c.session).toBe("s9");
    expect(bot.usage?.output_tokens).toBe(5);
  });
  it("does not mutate its input and ignores ping/done", () => {
    const c = base();
    const out = applyEvent(c, { type: "delta", text: "x" });
    expect(c.messages[1]!.content).toBe("");
    expect(applyEvent(out, { type: "done" })).toBe(out);
  });
});

describe("history", () => {
  it("drops failed questions and empty errored answers", () => {
    const msgs = [
      { role: "user" as const, content: "bad", failed: true },
      { role: "assistant" as const, content: "", error: "x" },
      { role: "user" as const, content: "ok", sources: ["a"] },
      { role: "assistant" as const, content: "fine" },
    ];
    expect(historyOf(msgs)).toEqual([
      { role: "user", content: "ok", sources: ["a"] },
      { role: "assistant", content: "fine", sources: undefined },
    ]);
    expect(canSave(msgs)).toBe(true);
    expect(savableMessages(msgs).map((m) => m.content)).toEqual(["ok", "fine"]);
  });
  it("dropLastTurn returns the question to ask again", () => {
    const c = base();
    const out = dropLastTurn(c);
    expect(out.question).toBe("q");
    expect(out.chat.messages).toEqual([]);
    expect(dropLastTurn({ ...c, messages: [] }).question).toBeNull();
  });
});

describe("prompts", () => {
  const prompts = parsePrompts([{ id: "query", title: "Query", text: " base " }, { id: "learn", title: "Learn", text: "teach" }, { title: "no id" }]);
  it("parses, picks with fallback, and tracks custom edits", () => {
    expect(prompts.map((p) => p.id)).toEqual(["query", "learn"]);
    expect(pick(prompts, "missing")?.id).toBe("query");
    const p = prompts[0]!;
    let edits = setEdit(p, {}, "changed");
    expect(isCustom(p, edits)).toBe(true);
    expect(systemFor(p, edits)).toBe("changed");
    edits = setEdit(p, edits, "base");
    expect(edits).toEqual({});
    expect(isCustom(p, edits)).toBe(false);
  });
});

describe("format", () => {
  it("prices at three precisions and builds the token line", () => {
    expect(fmtUsd(2.5)).toBe("$2.50");
    expect(fmtUsd(0.0123)).toBe("$0.012");
    expect(fmtUsd(0.0004)).toBe("$0.0004");
    expect(tokenLine({ input_tokens: 1000, cache_read_input_tokens: 200, output_tokens: 80, cost_usd: 0.5 })).toBe("1,200 in · 200 cached · 80 out · $0.500");
  });
});

describe("status", () => {
  it("narrows the loose dicts and labels backend and billing", () => {
    const v = parseStatus(chatStatus());
    expect(v.agentAvailable).toBe(true);
    expect(v.models.map((m) => m.id)).toEqual(["m1"]);
    expect(v.spend?.left).toBe(90);
    expect(effectiveBackend(v)).toBe("agent");
    expect(backendLabel(v).text).toBe("Agent · API key personal sk-ant-…abcd");
    expect(authValue(v)).toBe("key:personal");
    expect(authPayload("subscription")).toEqual({ auth_mode: "subscription" });
    expect(authPayload("key:x")).toEqual({ auth_mode: "api_key", active_key: "x" });
  });
  it("falls back to Direct when the SDK is missing and shows the subscription", () => {
    const v = parseStatus(chatStatus({ agent: { available: false, error: "no sdk" }, auth: { mode: "subscription", active_key: "", keys: [], keys_dir: "", subscription: { logged_in: true, plan: "max" } } }));
    expect(effectiveBackend(v)).toBe("direct");
    expect(backendLabel(v).text).toBe("Direct · subscription (max)");
  });
});
