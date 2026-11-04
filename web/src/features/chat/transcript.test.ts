import { applyEvent, emptyChat, type Chat } from "./thread";
import { splitFrames, toEvent } from "./sse";
import { ago, loadSessions, upsertSession } from "./sessions";

const ev = (event: string, data: unknown) => toEvent({ event, data: JSON.stringify(data) });

describe("agent-mode SSE events", () => {
  it("parses thinking, todo and user", () => {
    expect(ev("thinking", "hmm")).toEqual({ type: "thinking", text: "hmm" });
    expect(ev("user", { text: "also X" })).toEqual({ type: "user", text: "also X" });
    expect(ev("todo", { items: [{ content: "Read", status: "completed" }, { content: "Write", status: "weird" }, { content: "" }] })).toEqual({
      type: "todo",
      items: [{ content: "Read", status: "completed" }, { content: "Write", status: "pending" }],
    });
  });

  it("drops malformed frames of the new events", () => {
    expect(ev("thinking", { no: 1 })).toBeNull();
    expect(ev("todo", { items: "x" })).toBeNull();
    expect(ev("user", {})).toBeNull();
  });

  it("tool events carry status and a result preview", () => {
    expect(ev("tool", { name: "Grep", summary: "grep rank", id: "t1", status: "done", result: "3 hits" })).toEqual({
      type: "tool",
      step: { name: "Grep", summary: "grep rank", id: "t1", error: undefined, status: "done", result: "3 hits" },
    });
    const bad = ev("tool", { name: "Grep", summary: "", status: "bogus", result: 5 });
    expect(bad).toMatchObject({ step: { status: undefined, result: undefined } });
  });

  it("splits a burst of the new frames", () => {
    const { frames } = splitFrames('event: thinking\ndata: "a"\n\nevent: todo\ndata: {"items":[]}\n\n');
    expect(frames.map((f) => f.event)).toEqual(["thinking", "todo"]);
  });
});

function started(): Chat {
  return { ...emptyChat(), messages: [{ role: "user", content: "q" }, { role: "assistant", content: "" }] };
}

describe("applyEvent, agent mode", () => {
  it("accumulates thinking and times it when the answer starts", () => {
    let c = applyEvent(started(), { type: "thinking", text: "a" }, 1000);
    c = applyEvent(c, { type: "thinking", text: "b" }, 2000);
    c = applyEvent(c, { type: "delta", text: "ans" }, 5000);
    const bot = c.messages[1]!;
    expect(bot).toMatchObject({ thinking: "ab", thinkSecs: 4, content: "ans" });
  });

  it("keeps the latest todo list on the chat", () => {
    const c = applyEvent(started(), { type: "todo", items: [{ content: "x", status: "pending" }] });
    expect(c.todo).toEqual([{ content: "x", status: "pending" }]);
    expect(c.messages).toHaveLength(2);
  });

  it("tool results update the same line", () => {
    let c = applyEvent(started(), { type: "tool", step: { name: "Read", summary: "read a", id: "t", status: "running" } });
    c = applyEvent(c, { type: "tool", step: { name: "Read", summary: "read a", id: "t", status: "done", result: "text" } });
    expect(c.messages[1]!.trace).toEqual([{ name: "Read", summary: "read a", id: "t", status: "done", result: "text" }]);
  });

  it("a queued user message opens the next pair", () => {
    const c = applyEvent(started(), { type: "user", text: "and Y?" });
    expect(c.messages.map((m) => [m.role, m.content])).toEqual([["user", "q"], ["assistant", ""], ["user", "and Y?"], ["assistant", ""]]);
  });
});

describe("resumable sessions", () => {
  const chat = (over: Partial<Chat> = {}): Chat => ({
    id: "c1",
    session: "s1",
    messages: [{ role: "user", content: "What is rank?" }, { role: "assistant", content: "A number.", trace: [{ name: "Read", summary: "x" }] }],
    ...over,
  });

  it("stores chats that have a session and an answer, newest first, one per chat", () => {
    expect(upsertSession([], chat({ session: null }), 1)).toEqual([]);
    expect(upsertSession([], chat({ messages: [{ role: "user", content: "q" }, { role: "assistant", content: "" }] }), 1)).toEqual([]);
    const a = upsertSession([], chat(), 10);
    const b = upsertSession(a, chat({ id: "c2", session: "s2" }), 20);
    const again = upsertSession(b, chat(), 30);
    expect(again.map((e) => [e.id, e.last])).toEqual([["c1", 30], ["c2", 20]]);
    expect(again[0]).toMatchObject({ title: "What is rank?", session: "s1" });
    expect(again[0]!.messages[1]).not.toHaveProperty("trace");
  });

  it("loads nothing from a broken store, and words the age", () => {
    window.localStorage.setItem("kbchat.sessions", "{nope");
    expect(loadSessions()).toEqual([]);
    expect(ago(0, 30_000)).toBe("just now");
    expect(ago(0, 5 * 60_000)).toBe("5 min ago");
    expect(ago(0, 3 * 3600_000)).toBe("3 h ago");
    expect(ago(0, 2 * 86400_000)).toBe("2 d ago");
  });
});
