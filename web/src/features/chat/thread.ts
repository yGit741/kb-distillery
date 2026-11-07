import type { AskQuestion, ChatEvent, SourceHit, TodoItem, ToolStep, Usage } from "./sse";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  /** user: the pages first used for this question (sent back as history). */
  sources?: string[];
  /** assistant: pages used this turn and the agent's tool steps. */
  hits?: SourceHit[];
  trace?: ToolStep[];
  /** assistant, agent mode: the model's thinking text, when it started and how long it took (seconds). */
  thinking?: string;
  thinkStart?: number;
  thinkSecs?: number;
  usage?: Usage;
  notice?: string;
  /** assistant: a question from the agent that waits for the user's choice. */
  ask?: { id: string; questions: AskQuestion[] };
  meta?: string;
  error?: string;
  /** a question whose turn failed with no answer: shown, but not sent as history. */
  failed?: boolean;
}

export interface Chat {
  id: string;
  session: string | null;
  messages: ChatMessage[];
  /** agent mode: the agent's checklist (TodoWrite), pinned above the composer. */
  todo?: TodoItem[];
}

export const newChatId = (now = new Date(), rand = Math.random()) =>
  "kb-chat:" + now.toISOString().slice(0, 19).replace(/[-:T]/g, "") + "-" + rand.toString(36).slice(2, 8);

export const emptyChat = (): Chat => ({ id: newChatId(), session: null, messages: [] });

/** Fold one stream event into the assistant message being written (and the question it answers). */
export function applyEvent(
  chat: Chat,
  ev: ChatEvent,
  now = Date.now(),
): Chat {
  const msgs = chat.messages;
  const last = msgs.length - 1;
  if (last < 1 || msgs[last]!.role !== "assistant") return chat;
  if (ev.type === "todo") return { ...chat, todo: ev.items };
  if (ev.type === "user") {
    // a message queued into the running turn: it opens the next question/answer pair
    // a pending question moves with it, so the card stays on the last message where it can be answered
    const { ask, ...prev } = msgs[last]!;
    const next = { role: "assistant" as const, content: "", ...(ask ? { ask } : {}) };
    return { ...chat, messages: [...msgs.slice(0, last), prev, { role: "user", content: ev.text, sources: [] }, next] };
  }
  const bot = { ...msgs[last]! };
  if (ev.type === "thinking") {
    bot.thinking = (bot.thinking ?? "") + ev.text;
    bot.thinkStart ??= now;
    return { ...chat, messages: [...msgs.slice(0, last), bot] };
  }
  if (bot.thinkStart != null && bot.thinkSecs == null && (ev.type === "delta" || ev.type === "tool" || ev.type === "usage")) {
    bot.thinkSecs = Math.max(1, Math.round((now - bot.thinkStart) / 1000));
  }
  let user = msgs[last - 1]!;
  let session = chat.session;
  switch (ev.type) {
    case "delta":
      bot.content += ev.text;
      break;
    case "sources":
      bot.hits = ev.hits;
      user = { ...user, sources: ev.fresh };
      break;
    case "session":
      session = ev.id;
      break;
    case "tool": {
      const trace = [...(bot.trace ?? [])];
      const at = ev.step.id ? trace.findIndex((t) => t.id === ev.step.id) : -1;
      // a re-sent step (its result arrived) keeps what the first one said and the new one leaves out
      if (at >= 0) trace[at] = { ...trace[at]!, ...Object.fromEntries(Object.entries(ev.step).filter(([, v]) => v !== undefined)) } as ToolStep;
      else trace.push(ev.step);
      bot.trace = trace;
      break;
    }
    case "ask":
      bot.ask = { id: ev.id, questions: ev.questions };
      break;
    case "notice":
      bot.notice = ev.text;
      break;
    case "usage":
      bot.usage = ev.usage;
      break;
    case "error":
      bot.error = ev.message;
      delete bot.ask;
      break;
    case "done":
      if (!bot.ask) return chat;
      delete bot.ask;
      break;
    default:
      return chat;
  }
  return { ...chat, session, messages: [...msgs.slice(0, last - 1), user, bot] };
}

/** The question was answered (or is moot): drop it from the last assistant message. */
export function clearAsk(chat: Chat): Chat {
  const last = chat.messages.length - 1;
  if (last < 0 || !chat.messages[last]!.ask) return chat;
  const { ask: _ask, ...rest } = chat.messages[last]!;
  return { ...chat, messages: chat.messages.map((m, i) => (i === last ? rest : m)) };
}

/** What the server needs of earlier turns: no failed questions, no empty answers. */
export function historyOf(messages: ChatMessage[]): { role: string; content: string; sources?: string[] }[] {
  return messages
    .filter((m) => !m.failed && !(m.error && !m.content))
    .map((m) => ({ role: m.role, content: m.content, sources: m.sources }));
}

export function canSave(messages: ChatMessage[]): boolean {
  return messages.some((m) => m.role === "assistant" && m.content.trim() !== "");
}

/** Messages as written to the inbox: the tool trace and notices stay in the browser. */
export function savableMessages(messages: ChatMessage[]) {
  return messages
    .filter((m) => !m.failed && m.content)
    .map(({ role, content, sources, usage, meta }) => ({ role, content, sources, usage, meta }));
}

export const chatTitle = (messages: ChatMessage[]) =>
  (messages.find((m) => m.role === "user")?.content || "KB chat").split("\n")[0]!.slice(0, 80);

/** Drop the last question/answer pair; returns the question to ask again (or null). */
export function dropLastTurn(chat: Chat): { chat: Chat; question: string | null } {
  const msgs = chat.messages;
  const last = msgs.length - 1;
  if (last < 1 || msgs[last]!.role !== "assistant" || msgs[last - 1]!.role !== "user") return { chat, question: null };
  return { chat: { ...chat, messages: msgs.slice(0, last - 1) }, question: msgs[last - 1]!.content };
}
