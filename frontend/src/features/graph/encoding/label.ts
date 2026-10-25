import { pageDisplay } from "../displayNames";
import type { GNode } from "../types";

/** Which text a label shows: the short display name, the title as written, or the slug. */
export type TextField = "short" | "title" | "slug";

const STOP = new Set(["the", "a", "an", "of", "on", "and", "for", "in", "to", "with", "via", "from", "by", "at"]);
const QUESTION_LEAD = /^(does|do|is|are|can|could|what|why|how|which|when|where|should|will)\s+((is|are|do|does|there)\s+)?((the|a|an)\s+)?/i;

/** Trailing stop words go before the ellipsis ("bias of the…" -> "bias…"). */
const trimStop = (s: string): string => {
  let out = s;
  while (out && STOP.has((out.split(" ").pop() ?? "").toLowerCase())) out = out.split(" ").slice(0, -1).join(" ");
  return out;
};

/** The first words of `s` within `maxChars`, then "…"; a word longer than the budget is cut hard. */
function cutWords(s: string, maxChars: number): string {
  let out = "";
  for (const w of s.split(/\s+/)) {
    if ((out + " " + w).trim().length > maxChars) break;
    out = (out + " " + w).trim();
  }
  return `${trimStop(out) || s.slice(0, maxChars)}…`;
}

/**
 * The label's words, uncut. "short" takes the page's presentation name when it has one (./displayNames), else
 * drops a leading article, a subtitle after ":" or " - ", and parentheses; a question loses its question word
 * (its ring already says "question", so no "?" marker). `full` is the whole title as written.
 */
export function shortTitle(n: GNode, field: TextField, full = false): string {
  let s = field === "slug" ? n.id : n.title || n.id;
  if (full || field !== "short") return s;
  const picked = pageDisplay(n);
  if (picked) return picked;
  if (n.type === "question") {
    s = s.replace(QUESTION_LEAD, "").replace(/\?$/, "");
    s = s.charAt(0).toUpperCase() + s.slice(1);
  }
  return s.replace(/^(the|a|an)\s+/i, "").replace(/\s*[:(—–-]\s.*$/, "").replace(/\s*\(.*?\)\s*/g, " ").trim();
}

/** One-line label: `shortTitle` cut at a word boundary to `maxChars`; `full` is never cut. */
export function labelText(n: GNode, field: TextField, maxChars: number, full = false): string {
  const s = shortTitle(n, field, full);
  if (full) return s;
  if (field !== "short") return s.length <= maxChars ? s : `${s.slice(0, maxChars - 1)}…`;
  return s.length > maxChars ? cutWords(s, maxChars) : s;
}

/**
 * Word-boundary greedy fill into at most `maxLines` lines of `maxWidth` px; the last line ends in "…" (stop words
 * trimmed) when words remain. A word is never split: one wider than the budget stands alone on its line.
 * `maxWidth <= 0` is the one-line character cut of `labelText`.
 */
export function wrapLabel(s: string, maxWidth: number, maxLines: number, measure: (text: string) => number, maxChars: number): string[] {
  if (maxWidth <= 0) return [s.length <= maxChars ? s : cutWords(s, maxChars)];
  const words = s.split(/\s+/).filter(Boolean);
  if (!words.length) return [s];
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (!cur || measure(next) <= maxWidth) {
      cur = next;
      continue;
    }
    if (lines.length + 1 >= Math.max(1, maxLines)) {
      // the last line: shed words until the ellipsis fits too
      let last = trimStop(cur) || cur;
      while (last.includes(" ") && measure(`${last}…`) > maxWidth) last = trimStop(last.split(" ").slice(0, -1).join(" ")) || last.split(" ")[0]!;
      // one word still too wide: a character cut rather than an overflow
      return [...lines, measure(`${last}…`) > maxWidth ? cutWords(last, maxChars) : `${last}…`];
    }
    lines.push(cur);
    cur = w;
  }
  if (cur) lines.push(cur);
  return lines;
}
