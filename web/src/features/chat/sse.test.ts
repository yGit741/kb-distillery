import { readEvents, splitFrames, toEvent, type ChatEvent } from "./sse";

const enc = (s: string) => new TextEncoder().encode(s);
function streamOf(chunks: string[], hang = false): ReadableStream<Uint8Array> {
  let i = 0;
  return new ReadableStream({
    pull(c) {
      if (i < chunks.length) c.enqueue(enc(chunks[i++]!));
      else if (!hang) c.close();
      else return new Promise(() => {});
    },
  });
}

describe("splitFrames", () => {
  it("keeps an incomplete frame as the rest and joins multi-line data", () => {
    const { frames, rest } = splitFrames('event: delta\ndata: "a"\n\nevent: delta\ndata: "b');
    expect(frames).toEqual([{ event: "delta", data: '"a"' }]);
    expect(rest).toBe('event: delta\ndata: "b');
    expect(splitFrames("event: x\ndata: 1\ndata: 2\n\n").frames[0]!.data).toBe("1\n2");
  });
  it("reads CRLF framing and treats comment lines as pings", () => {
    const { frames } = splitFrames(": ping\r\n\r\nevent: done\r\ndata: {}\r\n\r\n");
    expect(frames.map((f) => f.event)).toEqual(["ping", "done"]);
  });
});

describe("toEvent", () => {
  it("types each event name", () => {
    expect(toEvent({ event: "delta", data: '"hi"' })).toEqual({ type: "delta", text: "hi" });
    expect(toEvent({ event: "session", data: '{"id":"s1"}' })).toEqual({ type: "session", id: "s1" });
    expect(toEvent({ event: "error", data: '{"error":"boom"}' })).toEqual({ type: "error", message: "boom" });
    expect(toEvent({ event: "sources", data: '{"hits":[{"slug":"a","score":2,"summary":"s","in_context":true},{"x":1}],"new":["a"]}' })).toEqual({
      type: "sources",
      hits: [{ slug: "a", score: 2, summary: "s", in_context: true }],
      fresh: ["a"],
    });
    expect(toEvent({ event: "tool", data: '{"name":"Read","summary":"read a","id":"t1","error":true}' })).toEqual({
      type: "tool",
      step: { name: "Read", summary: "read a", id: "t1", error: true },
    });
  });
  it("ignores unknown names and malformed JSON", () => {
    expect(toEvent({ event: "weird", data: "{}" })).toBeNull();
    expect(toEvent({ event: "delta", data: "{not json" })).toBeNull();
    expect(toEvent({ event: "delta", data: "42" })).toBeNull();
    expect(toEvent({ event: "", data: "" })).toBeNull();
  });
});

describe("ask and web sources", () => {
  it("parses an ask event and drops questions without options", () => {
    const ev = toEvent({ event: "ask", data: JSON.stringify({ id: "a1", questions: [
      { question: "Pick", multiSelect: true, options: [{ label: "A", description: "x" }, { label: "" }] },
      { question: "No options", options: [] },
    ] }) });
    expect(ev).toEqual({ type: "ask", id: "a1", questions: [{ question: "Pick", header: undefined, multiSelect: true, options: [{ label: "A", description: "x" }] }] });
    expect(toEvent({ event: "ask", data: JSON.stringify({ questions: [] }) })).toBeNull();
  });
  it("keeps the kind of a hit; refuses a web hit that is not http(s)", () => {
    const ev = toEvent({ event: "sources", data: JSON.stringify({ hits: [
      { slug: "a", score: 1 },
      { kind: "web", url: "https://x.org/p", title: "P" },
      { kind: "web", url: "javascript:alert(1)", title: "bad" },
    ], new: ["a"] }) });
    expect(ev).toMatchObject({ type: "sources", hits: [{ slug: "a" }, { kind: "web", url: "https://x.org/p", title: "P" }] });
    expect((ev as { hits: unknown[] }).hits).toHaveLength(2);
  });
});

describe("readEvents", () => {
  it("reassembles frames split across chunks, drops pings, batches per chunk", async () => {
    const batches: ChatEvent[][] = [];
    await readEvents(
      streamOf(["event: del", 'ta\ndata: "He"\n\n: ping\n\nevent: delta\ndata: "llo"\n\n', "event: done\ndata: {}\n\n"]),
      (e) => batches.push(e),
    );
    expect(batches.flat().map((e) => e.type)).toEqual(["delta", "delta", "done"]);
    expect(batches[0]).toHaveLength(2);
  });
  it("flushes a final frame without the trailing blank line", async () => {
    const out: ChatEvent[] = [];
    await readEvents(streamOf(['event: delta\ndata: "x"\n']), (e) => out.push(...e));
    expect(out).toEqual([{ type: "delta", text: "x" }]);
  });
  it("rejects with AbortError when the signal fires", async () => {
    const ctl = new AbortController();
    const p = readEvents(streamOf(['event: delta\ndata: "a"\n\n'], true), () => ctl.abort(), ctl.signal);
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
  });
});
