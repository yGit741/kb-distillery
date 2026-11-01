import type { ChatEvent, SourceHit, ToolStep, Usage } from "./sse";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  /** user: the pages first used for this question (sent back as history). */
  sources?: string[];
  /** assistant: pages used this turn and the agent's tool steps. */
  hits?: SourceHit[];
  trace?: ToolStep[];
  usage?: Usage;
  notice?: string;
  meta?: string;
  error?: string;
  /** a question whose turn failed with no answer: shown, but not sent as history. */
  failed?: boolean;
}

export interface Chat {
  id: string;
  session: string | null;
  messages: ChatMessage[];
}

export const newChatId = (now = new Date(), rand = Math.random()) =>
  "kb-chat:" + now.toISOString().slice(0, 19).replace(/[-:T]/g, "") + "-" + rand.toString(36).slice(2, 8);

export const emptyChat = (): Chat => ({ id: newChatId(), session: null, messages: [] });

/** Fold one stream event into the assistant message being written (and the question it answers). */
export function applyEvent(
  chat: Chat,
  ev: ChatEvent,
): Chat {
  const msgs = chat.messages;
  const last = msgs.length - 1;
  if (last < 1 || msgs[last]!.role !== "assistant") return chat;
  const bot = { ...msgs[last]! };
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
      if (at >= 0) trace[at] = { ...trace[at]!, ...ev.step };
      else trace.push(ev.step);
      bot.trace = trace;
      break;
    }
    case "notice":
      bot.notice = ev.text;
      break;
    case "usage":
      bot.usage = ev.usage;
      break;
    case "error":
      bot.error = ev.message;
      break;
    default:
      return chat;
  }
  return { ...chat, session, messages: [...msgs.slice(0, last - 1), user, bot] };
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
