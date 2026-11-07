/** Typed server-sent-events reader for POST /api/chat. Pure parsing here; no fetch, no React. */

export interface SourceHit {
  /** "wiki" (default) or "web": a web hit carries url and title and has no slug. */
  kind?: "wiki" | "web";
  slug: string;
  url?: string;
  title?: string;
  score: number;
  summary: string;
  in_context: boolean;
}
export interface AskOption {
  label: string;
  description?: string;
}
export interface AskQuestion {
  question: string;
  header?: string;
  multiSelect?: boolean;
  options: AskOption[];
}
export interface ToolStep {
  name: string;
  summary: string;
  id?: string;
  error?: boolean;
  /** agent mode: running until its result arrives. */
  status?: "running" | "done" | "error";
  /** agent mode: the first ~300 characters of the tool's output. */
  result?: string;
  /** page slugs a search or listing returned (at most 50); absent when unknown. */
  seen?: string[];
  /** page slugs whose content the step opened (at most 50); absent when unknown. */
  read?: string[];
  /** the model's turn this call was sent in (1-based, shared by calls sent together); absent on old messages */
  round?: number;
  /** what the call does: shortlist, meaning, graph, raw, alias, keyword, files, open, attachment, web-search, web-source, other */
  kind?: string;
  /** the call's own words: search terms, grep pattern, cypher, web query */
  query?: string;
  /** an opened web page */
  url?: string;
  /** the hosts a web search returned */
  domains?: string[];
}
export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
}
export interface Usage {
  input_tokens?: number;
  output_tokens?: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
  cost_usd?: number;
  est_cost_usd?: number;
  billing?: string;
  num_turns?: number;
  model?: string;
  spend?: Record<string, unknown>;
}

export type ChatEvent =
  | { type: "sources"; hits: SourceHit[]; fresh: string[] }
  | { type: "session"; id: string }
  | { type: "tool"; step: ToolStep }
  | { type: "ask"; id: string; questions: AskQuestion[] }
  | { type: "thinking"; text: string }
  | { type: "todo"; items: TodoItem[] }
  | { type: "user"; text: string }
  | { type: "notice"; text: string }
  | { type: "delta"; text: string }
  | { type: "usage"; usage: Usage }
  | { type: "error"; message: string }
  | { type: "done" }
  | { type: "ping" };

export interface RawFrame {
  event: string;
  data: string;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
/** A short list of page slugs from the wire, or undefined when there is none. */
const slugList = (v: unknown): string[] | undefined => {
  const list = (Array.isArray(v) ? v : []).filter((s): s is string => typeof s === "string" && s !== "").slice(0, 50);
  return list.length ? list : undefined;
};
const num = (v: unknown, d = 0) => (typeof v === "number" && Number.isFinite(v) ? v : d);

/**
 * Split a text buffer into complete frames. Returns the frames and the unconsumed rest.
 * A frame is blank-line terminated; `: …` lines are comments (the server's keep-alive ping), `data:` lines join with \n.
 */
export function splitFrames(buffer: string): { frames: RawFrame[]; rest: string } {
  const text = buffer.replace(/\r\n?/g, "\n");
  const frames: RawFrame[] = [];
  let from = 0;
  for (let cut = text.indexOf("\n\n", from); cut !== -1; cut = text.indexOf("\n\n", from)) {
    frames.push(parseFrame(text.slice(from, cut)));
    from = cut + 2;
  }
  return { frames, rest: text.slice(from) };
}

function parseFrame(block: string): RawFrame {
  let event = "";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) {
      event ||= "ping";
    } else if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data.push(line.slice(5).replace(/^ /, ""));
    }
  }
  return { event, data: data.join("\n") };
}

/** Frame -> typed event; unknown or malformed frames give null (ignored, never thrown). */
export function toEvent(frame: RawFrame): ChatEvent | null {
  if (frame.event === "ping") return { type: "ping" };
  if (!frame.event) return null;
  let payload: unknown;
  try {
    payload = frame.data ? JSON.parse(frame.data) : {};
  } catch {
    return null;
  }
  switch (frame.event) {
    case "delta":
      return typeof payload === "string" ? { type: "delta", text: payload } : null;
    case "sources": {
      if (!isObj(payload)) return null;
      const hits = (Array.isArray(payload.hits) ? payload.hits : []).filter(isObj).map((h): SourceHit => {
        const base = { score: num(h.score), summary: typeof h.summary === "string" ? h.summary : "", in_context: h.in_context === true };
        if (h.kind === "web") {
          const url = typeof h.url === "string" && /^https?:\/\//.test(h.url) ? h.url : "";
          return { ...base, kind: "web", slug: "", url, title: typeof h.title === "string" && h.title ? h.title : url };
        }
        return { ...base, ...(h.kind === "wiki" ? { kind: "wiki" as const } : {}), slug: String(h.slug ?? "") };
      });
      const fresh = (Array.isArray(payload.new) ? payload.new : []).filter((s): s is string => typeof s === "string");
      return { type: "sources", hits: hits.filter((h) => (h.kind === "web" ? h.url : h.slug)), fresh };
    }
    case "session":
      return isObj(payload) && typeof payload.id === "string" ? { type: "session", id: payload.id } : null;
    case "tool":
      if (!isObj(payload)) return null;
      return {
        type: "tool",
        step: {
          name: String(payload.name ?? ""),
          summary: typeof payload.summary === "string" ? payload.summary : "",
          id: typeof payload.id === "string" ? payload.id : undefined,
          error: payload.error === true ? true : undefined,
          status: payload.status === "running" || payload.status === "done" || payload.status === "error" ? payload.status : undefined,
          result: typeof payload.result === "string" ? payload.result : undefined,
          seen: slugList(payload.seen),
          read: slugList(payload.read),
          round: typeof payload.round === "number" && payload.round >= 1 ? Math.floor(payload.round) : undefined,
          kind: typeof payload.kind === "string" && payload.kind ? payload.kind : undefined,
          query: typeof payload.query === "string" && payload.query ? payload.query : undefined,
          url: typeof payload.url === "string" && payload.url ? payload.url : undefined,
          domains: slugList(payload.domains),
        },
      };
    case "ask": {
      if (!isObj(payload) || typeof payload.id !== "string") return null;
      const questions = (Array.isArray(payload.questions) ? payload.questions : []).filter(isObj).map((q): AskQuestion => ({
        question: String(q.question ?? ""),
        header: typeof q.header === "string" ? q.header : undefined,
        multiSelect: q.multiSelect === true,
        options: (Array.isArray(q.options) ? q.options : []).filter(isObj).map((o) => ({
          label: String(o.label ?? ""),
          description: typeof o.description === "string" ? o.description : undefined,
        })).filter((o) => o.label),
      })).filter((q) => q.question && q.options.length);
      return questions.length ? { type: "ask", id: payload.id, questions } : null;
    }
    case "thinking":
      return typeof payload === "string" ? { type: "thinking", text: payload } : null;
    case "todo": {
      if (!isObj(payload) || !Array.isArray(payload.items)) return null;
      const items = payload.items.filter(isObj).map((t): TodoItem => ({
        content: String(t.content ?? ""),
        status: t.status === "completed" || t.status === "in_progress" ? t.status : "pending",
      }));
      return { type: "todo", items: items.filter((t) => t.content) };
    }
    case "user":
      return isObj(payload) && typeof payload.text === "string" ? { type: "user", text: payload.text } : null;
    case "notice":
      return isObj(payload) && typeof payload.text === "string" ? { type: "notice", text: payload.text } : null;
    case "usage":
      return isObj(payload) ? { type: "usage", usage: payload as Usage } : null;
    case "error":
      return { type: "error", message: isObj(payload) && typeof payload.error === "string" ? payload.error : "The chat failed." };
    case "done":
      return { type: "done" };
    default:
      return null;
  }
}

/**
 * Read a streaming response to its end. `onEvents` gets every event of one network chunk at once, so a
 * burst of deltas costs one render. Rejects with an AbortError when `signal` fires.
 */
export async function readEvents(
  body: ReadableStream<Uint8Array>,
  onEvents: (events: ChatEvent[]) => unknown,
  signal?: AbortSignal,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const onAbort = () => void reader.cancel().catch(() => {});
  signal?.addEventListener("abort", onAbort);
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (signal?.aborted) throw new DOMException("aborted", "AbortError");
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { frames, rest } = splitFrames(buffer);
      buffer = rest;
      const events = frames.map(toEvent).filter((e): e is ChatEvent => e !== null && e.type !== "ping");
      if (events.length) await onEvents(events);
    }
    const tail = splitFrames(buffer + "\n\n").frames.map(toEvent).filter((e): e is ChatEvent => e !== null && e.type !== "ping");
    if (tail.length) await onEvents(tail);
  } finally {
    signal?.removeEventListener("abort", onAbort);
  }
}
