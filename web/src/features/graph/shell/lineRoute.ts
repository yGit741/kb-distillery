import { commandScore, type Command } from "./commands";
import { looksLikeShape } from "./shellStore";

/**
 * Where a plain line goes on Enter (flag line-routing): the rules here read it first, instantly and without a model.
 * A line they cannot place goes to `POST /api/line/route` (the shared LLM tool), and a failure there reads as a search.
 */
export type LineIntent = "search" | "view" | "command" | "ask";

export interface LineRoute {
  intent: LineIntent;
  /** The text to pass on. */
  text: string;
  /** For `command`: the command's id. For `search`: the page to open when a title matched exactly. */
  id?: string;
}

/** View words beyond the shape words of `looksLikeShape`: a longer line with one of them changes the view, like `>`. */
const VIEW_WORDS = /\b(filter|filter out|show only|only|remove|without|degree|colou?r|size|group|layout|hide)\b/i;
/** A short line changes the view only when it starts with one of these ("group theory" stays a page search). */
const VIEW_START = /^(filter|show only|only|remove|hide)\b/i;
const QUESTION_START = /^(what|why|how|who|which|when|explain|summari[sz]e|compare)\b/i;
/** A command name counts as a strong match from this score (share of words that fit, see commandScore). */
export const STRONG_COMMAND = 0.66;
/** Lines up to this many words that the rules cannot place are read as a page search; longer ones ask the model. */
export const SHORT_WORDS = 3;

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");

/** Whether a line reads as a view change: the shape words, or the wider view words (flag line-routing). */
export function readsAsView(text: string): boolean {
  const t = text.trim();
  if (looksLikeShape(t) || VIEW_START.test(t)) return true;
  return t.split(/\s+/).length > SHORT_WORDS && VIEW_WORDS.test(t);
}

/** Whether a line reads as a question for the chat. */
export function readsAsQuestion(text: string): boolean {
  const t = text.trim();
  return t.endsWith("?") || QUESTION_START.test(t);
}

/** The best command for a line when its name fits strongly; undefined otherwise. */
export function strongCommand(commands: readonly Command[], text: string): Command | undefined {
  let best: { c: Command; s: number } | undefined;
  for (const c of commands) {
    const s = commandScore(c, text);
    if (s >= STRONG_COMMAND && (!best || s > best.s)) best = { c, s };
  }
  return best?.c;
}

interface RuleCtx {
  /** The pages on the graph (an exact title or id opens that page). */
  pages: readonly { id: string; title: string }[];
  commands: readonly Command[];
  /** The chat is there (not on the share build). */
  canAsk: boolean;
}

/**
 * The rules, in order: an exact page title, a line ending in "?", view words, a question word, a strong command name,
 * then any short line as a page search. Null: the rules cannot place it, so the model reads it.
 */
export function routeByRules(raw: string, ctx: RuleCtx): LineRoute | null {
  const text = raw.trim();
  if (!text) return null;
  const n = norm(text);
  const short = n.split(" ").length <= SHORT_WORDS;
  // a strong title match: the exact title or id, or a title holding the line as whole words
  const within = new RegExp(`(^|\\W)${n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|\\W)`);
  const page = ctx.pages.find((p) => norm(p.title) === n || p.id.toLowerCase() === n);
  if (page) return { intent: "search", text, id: page.id };
  // a title holding the whole line as words: the search's own ranking picks the page then
  if (ctx.pages.some((p) => within.test(norm(p.title)))) return { intent: "search", text };
  if (ctx.canAsk && text.endsWith("?")) return { intent: "ask", text };
  if (readsAsView(text)) return { intent: "view", text };
  if (ctx.canAsk && readsAsQuestion(text)) return { intent: "ask", text };
  const cmd = strongCommand(ctx.commands, text);
  if (cmd) return { intent: "command", text, id: cmd.id };
  if (short) return { intent: "search", text };
  return null;
}
