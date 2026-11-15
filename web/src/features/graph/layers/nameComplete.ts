import { findPages } from "../pageSearch";
import type { GNode } from "../types";
import { nameFor } from "./names";
import { distance } from "./sentence";

/**
 * Page names inside a `>` line (flag graph-algos): where the line ends in a page name being typed, which pages it may
 * be, and the line with one of them put in. A name is expected after "of", "between", "from", "near", "around",
 * "like", "containing", "close to", "next to", "similar to", and after "and" / "to" once the line has said "between",
 * "from", "connects" or "common neighbours", so "hide people and orphans" offers no pages.
 */

export interface NameSlot {
  /** Where the name starts in the line (its opening quote, when it has one). */
  start: number;
  /** What is typed of it so far, without the quote. */
  partial: string;
}

const TRIGGERS = /(?:^|\s)(close to|next to|similar to|of|between|from|near|around|like|containing|and|to)\s+/gi;
const PAIRED = /\b(?:between|from|connects?|links?|common neighbou?rs|shared neighbou?rs|mutual neighbou?rs)\b/i;
/** Words that stand for a page without naming one, or start the next clause: no name is being typed. */
const NOT_A_NAME = /^(?:(?:this|this page|here|the focus|the current page|my favou?rites|favou?rites)$|(?:their|its|hide|show|only|exclude|colou?r|size)\b|\d+\+?(?:\s|$))/i;
const MAX_WORDS = 6;

/** Every place the line may end in a page name, earliest first: after each trigger word, up to the end of the line. */
export function nameSlots(line: string): NameSlot[] {
  const out: NameSlot[] = [];
  for (const m of line.matchAll(TRIGGERS)) {
    const word = m[1]!.toLowerCase();
    const at = m.index! + m[0].length;
    // "and" / "to" take a second name only in a clause that named a pair ("between A and B"), not a later clause
    if ((word === "and" || word === "to") && !PAIRED.test(clauseBefore(line, m.index!))) continue;
    // a trigger word inside a quoted name ("Signal and noise") is part of the name
    if (inQuote(line, m.index!)) continue;
    let partial = line.slice(at);
    if (/^["“]/.test(partial)) {
      partial = partial.slice(1);
      if (/["”]/.test(partial)) continue; // the name is closed
    } else if (/[,;"“]|\s+then\s+/.test(partial)) continue; // the line has moved on to another clause
    const bare = partial.trim();
    if (bare.length < 2 || NOT_A_NAME.test(bare) || bare.split(/\s+/).length > MAX_WORDS) continue;
    out.push({ start: at, partial: bare });
  }
  return out;
}

/** The page name the line ends in, read from the last trigger word; null when the line does not end in a name. */
export const nameSlot = (line: string): NameSlot | null => nameSlots(line).at(-1) ?? null;

/**
 * The name being typed and the pages it may be. The earliest trigger whose text names a page wins, so a title that
 * holds a trigger word itself ("near theory of mi" for "Theory of mind") is read whole; a pair's second name
 * ("between Learning theory and ju") is read from its own trigger.
 */
export function completeName(line: string, nodes: readonly GNode[], limit = 6): { slot: NameSlot; pages: GNode[] } | null {
  for (const slot of nameSlots(line)) {
    const pages = namePages(nodes, slot.partial, limit);
    if (pages.length) return { slot, pages };
  }
  return null;
}

/** The text of the clause a position is in, up to that position (a clause ends at a comma, a semicolon or "then"). */
function clauseBefore(line: string, at: number): string {
  const before = line.slice(0, at);
  let from = 0;
  for (const m of before.matchAll(/[,;]|\sthen\s/gi)) if (!inQuote(line, m.index!)) from = m.index! + m[0].length;
  return before.slice(from);
}

function inQuote(line: string, at: number): boolean {
  let open = false;
  for (let i = 0; i < at; i++) {
    const ch = line[i];
    if (ch === '"') open = !open;
    else if (ch === "“") open = true;
    else if (ch === "”") open = false;
  }
  return open;
}

const words = (s: string) => s.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
/** A typed word against a title word: the start of it, or the word or its start within a small typo. */
function wordFits(q: string, t: string, last: boolean): boolean {
  if (t.startsWith(q)) return true;
  const max = q.length >= 7 ? 2 : q.length >= 4 ? 1 : 0;
  if (!max) return false;
  return distance(q, t, max) <= max || (last && t.length > q.length && distance(q, t.slice(0, q.length), max) <= max);
}

/**
 * The pages a partial name may mean, best first: the search's own title and slug matches; when there are none, titles
 * that fit word by word within a small typo ("lerning th" finds "Learning theory").
 */
export function namePages(nodes: readonly GNode[], partial: string, limit = 6): GNode[] {
  const out = findPages(nodes, partial, limit);
  if (out.length) return out;
  const qs = words(partial);
  if (!qs.length) return out;
  const loose = nodes
    .filter((n) => {
      const ts = words(n.title || n.id);
      return qs.every((q, i) => ts.some((t) => wordFits(q, t, i === qs.length - 1)));
    })
    .sort((a, b) => (b.inDegree || 0) - (a.inDegree || 0));
  return loose.slice(0, limit);
}

/** The line with the name it ends in replaced by the page's name in quotes and a space, ready for the next word. */
export function putName(line: string, slot: NameSlot, page: GNode, unique: ReadonlySet<string>): string {
  return `${line.slice(0, slot.start)}${nameFor(page, unique)} `;
}
