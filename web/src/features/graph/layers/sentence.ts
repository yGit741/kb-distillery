import { FAVORITES, FOCUS, makeLayer, type EdgeCond, type Layer, type NodeCond, type Op } from "./model";
import { print } from "./grammar";
import { LINE_COPY } from "../shell/copy";

/**
 * Casual English into layers (flag graph-intent): rules only, no model call. Text it cannot read comes back as
 * `unknown`, which the shell sends down the older shape path. Every word it understands lives in a table below.
 */

export interface Sentence {
  layers: Layer[];
  /** Each layer written in the query language (names as typed, before they are resolved). */
  lines: string[];
  /** The text that could not be read; set when no layers are returned. */
  unknown?: string;
}

// ---- the words, in one place
const NUM_OPS: Record<string, Op> = {
  under: "<",
  below: "<",
  "fewer than": "<",
  "less than": "<",
  over: ">",
  above: ">",
  "more than": ">",
  "at least": ">=",
  "at most": "<=",
  exactly: "=",
  ">=": ">=",
  "<=": "<=",
  ">": ">",
  "<": "<",
  "=": "=",
};
const OP_RE = Object.keys(NUM_OPS).sort((a, b) => b.length - a.length).map((k) => k.replace(/[<>=]/g, (c) => `\\${c}`)).join("|");

/** Words that stand for a condition on pages. */
const NODE_WORDS: [RegExp, NodeCond[]][] = [
  [/\bnon[- ]?(?:orphans?|isolated)\b|\bconnected (?:pages|nodes)\b/, [{ t: "degree", op: ">", n: 0 }]],
  [/\b(?:orphans?|isolated)\b/, [{ t: "degree", op: "=", n: 0 }]],
  [/\bhubs?\b/, [{ t: "degree", op: ">=", n: 8 }]],
  [/\bleaf\b|\bleaves\b/, [{ t: "degree", op: "=", n: 1 }]],
  [/\bfavou?rites?\b/, [{ t: "favorite" }]],
  [/\bcontradictions?\b/, [{ t: "hasEdge", type: "contradicts" }]],
];
/** Words that stand for a link type. */
const EDGE_WORDS: Record<string, string> = { mentions: "mentions", supports: "supports", contradicts: "contradicts", cites: "cites", extends: "extends" };
/** Plural or loose page type words. */
const TYPE_WORDS: Record<string, string> = { papers: "paper", paper: "paper", ideas: "idea", idea: "idea", questions: "question", question: "question", people: "person", person: "person", courses: "course", course: "course", topics: "topic", topic: "topic", books: "book", book: "book", concepts: "concept", concept: "concept", claims: "claim", claim: "claim" };
/** Spoken colour and size fields to the graph's own. */
const COLOR_FIELDS: Record<string, string> = { kind: "type", links: "degree", connections: "degree", maturity: "status" };
const SIZE_FIELDS: Record<string, string> = { degree: "connections", links: "connections", connections: "connections", same: "uniform" };
const WIDTHS: Record<string, "thick" | "thin"> = { thicken: "thick", widen: "thick", thicker: "thick", bolden: "thick", thin: "thin", thinner: "thin", thinnen: "thin" };
const SINCE: [RegExp, (m: RegExpMatchArray) => number][] = [
  [/\b(?:added|created|new) (?:in )?(?:this|the last) month\b/, () => 30],
  [/\b(?:added|created|new) (?:in )?(?:this|the last) week\b/, () => 7],
  [/\b(?:added|created|new) (?:today|this day)\b/, () => 1],
  [/\b(?:added|created|new) in the last (\d+) days?\b/, (m) => Number(m[1])],
];
const STOP = new Set(["nodes", "node", "pages", "page", "that", "which", "are", "is", "the", "a", "an", "with", "and", "only", "all", "show", "me", "of", "in", "have", "has", "just", "find", "keep", "those", "these", "any", "edges", "edge", "links", "link", "connections", "having", "where"]);

const unq = (s: string) => s.trim().replace(/^["'“‘]+|["'”’]+$/g, "").trim();
const nameOf = (s: string): string => {
  const n = unq(s);
  if (/^(?:my )?favou?rites?$/i.test(n)) return FAVORITES;
  if (/^(?:this|this page|the focus|here|the current page)$/i.test(n)) return FOCUS;
  return n;
};

interface Found<C> {
  at: number;
  conds: C[];
}

/** Takes a match out of the working text, leaving blanks so later indices still point into the original. */
function take(work: { s: string }, re: RegExp): RegExpMatchArray | null {
  const m = work.s.match(re);
  if (!m || m.index === undefined) return null;
  work.s = work.s.slice(0, m.index) + " ".repeat(m[0].length) + work.s.slice(m.index + m[0].length);
  return m;
}

function filterClause(clause: string): Layer | null {
  let rest = clause.trim();
  let kind: "show" | "hide" = "show";
  if (/^hide\s+/i.test(rest)) {
    kind = "hide";
    rest = rest.replace(/^hide\s+/i, "");
  }
  rest = rest.replace(/^(?:only|just|show(?: me)?|find|keep)\s+/i, "");
  const work = { s: rest };

  // pages that have a link of some type: "nodes that share a contradicts edge"
  const has = rest.match(/^(?:nodes|pages)?\s*(?:that |which )?(?:share|have|has|with|having)\s+an?\s+([\w-]+)\s+(?:edge|link)s?$/i);
  if (has) return makeLayer(kind, "nodes", { nodes: [{ t: "hasEdge", type: has[1]!.toLowerCase() }] });

  const edgeWord = rest.match(/\b([\w-]+)\s+(?:edges?|links?)\b/i);
  const bareEdge = Object.keys(EDGE_WORDS).find((w) => new RegExp(`^${w}\\b`, "i").test(rest));
  const edges = !!edgeWord || (kind === "hide" && !!bareEdge);

  const nodeFound: Found<NodeCond>[] = [];
  const edgeConds: EdgeCond[] = [];
  let num: { op: Op; n: number } | null = null;

  if (edges) {
    const t = edgeWord && !STOP.has(edgeWord[1]!.toLowerCase()) ? edgeWord[1]!.toLowerCase() : bareEdge;
    if (t) edgeConds.push({ t: "type", value: EDGE_WORDS[t] ?? t });
    if (edgeWord) take(work, new RegExp(`\\b${edgeWord[1]}\\s+(?:edges?|links?)\\b`, "i"));
    else if (bareEdge) take(work, new RegExp(`^${bareEdge}\\b`, "i"));
  } else {
    // order of appearance is the order of the conditions
    const hops = take(work, /\bwithin (\d+) hops? (?:of|from) (.+?)(?=\s+(?:with|and|that|where|which|added|created|having|no)\b|$)/i);
    if (hops) nodeFound.push({ at: hops.index!, conds: [{ t: "hops", n: Number(hops[1]), of: nameOf(hops[2]!) }] });
    const since = SINCE.map(([re, days]) => [take(work, re), days] as const).find(([m]) => m);
    if (since?.[0]) nodeFound.push({ at: since[0].index!, conds: [{ t: "createdWithin", days: since[1](since[0]) }] });
    const no = take(work, /\b(?:with )?no ([\w-]+) notes?\b/i);
    if (no) nodeFound.push({ at: no.index!, conds: [{ t: "not", cond: { t: "linkedFromType", type: no[1]!.toLowerCase() } }] });
    for (const [re, conds] of NODE_WORDS) {
      const m = take(work, new RegExp(re.source, "i"));
      if (m) nodeFound.push({ at: m.index!, conds });
    }
  }

  const cmp = take(work, new RegExp(`\\b(?:with |having )?(?:(degree|links|connections|count) )?(${OP_RE})\\s*(\\d+)\\b`, "i"));
  if (cmp) num = { op: NUM_OPS[cmp[2]!.toLowerCase()]!, n: Number(cmp[3]) };

  // what is left must be filler, or one page type
  const left = work.s.toLowerCase().split(/[^a-z-]+/).filter((w) => w && !STOP.has(w));
  let type: string | undefined;
  if (left.length === 1 && !edges && TYPE_WORDS[left[0]!]) type = TYPE_WORDS[left[0]!];
  else if (left.length) return null;

  if (edges) {
    if (num) edgeConds.push({ t: "count", op: num.op, n: num.n });
    return edgeConds.length ? makeLayer(kind, "edges", { edges: edgeConds }) : null;
  }
  const conds: NodeCond[] = [];
  if (type) conds.push({ t: "type", value: type });
  if (num) nodeFound.push({ at: cmp!.index!, conds: [{ t: "degree", op: num.op, n: num.n }] });
  conds.push(...nodeFound.sort((a, b) => a.at - b.at).flatMap((f) => f.conds));
  // a type word leads; the rest keep the order they were said in
  return conds.length ? makeLayer(kind, "nodes", { nodes: conds }) : null;
}

function clauseLayers(clause: string): Layer[] | null {
  const c = clause.trim();
  let m = c.match(/^(?:colou?r)(?:ed)?(?: the)?(?: nodes| pages)? by ([\w-]+)$/i);
  if (m) {
    const f = m[1]!.toLowerCase();
    return [makeLayer("style", "nodes", {}, "", { style: { color: ((COLOR_FIELDS[f] ?? f) as never) } })];
  }
  m = c.match(/^(?:size|scale)(?: the)?(?: nodes| pages)? by ([\w-]+)$/i);
  if (m) {
    const f = m[1]!.toLowerCase();
    return [makeLayer("style", "nodes", {}, "", { style: { size: ((SIZE_FIELDS[f] ?? f) as never) } })];
  }
  m = c.match(/^(thicken|widen|thicker|thin|thinner)(?: the)?\s+(.*)$/i);
  if (m) {
    const w = WIDTHS[m[1]!.toLowerCase()]!;
    const what = m[2]!.trim();
    if (/^(?:all )?(?:edges|links)$/i.test(what)) return [makeLayer("style", "edges", {}, "", { style: { width: w } })];
    const t = what.match(/^([\w-]+)\s+(?:edges?|links?)$/i);
    if (t) return [makeLayer("style", "edges", { edges: [{ t: "type", value: EDGE_WORDS[t[1]!.toLowerCase()] ?? t[1]!.toLowerCase() }] }, "", { style: { width: w } })];
    return null;
  }
  m = c.match(/^(?:what|how) (?:connects?|links?) (.+?) (?:and|to|with) (.+)$/i) ?? c.match(/^(?:show )?(?:paths?|connections?) between (.+?) and (.+)$/i);
  if (m) return [makeLayer("show", "nodes", { nodes: [{ t: "paths", a: nameOf(m[1]!), b: nameOf(m[2]!), n: 4 }] })];
  m = c.match(/^(?:(?:show )?(?:the )?neighbou?rs of|neighbou?rhood of|expand) (.+)$/i);
  if (m) {
    const of = nameOf(m[1]!);
    return [makeLayer("show", "nodes", { nodes: [{ t: "hops", of, n: 1 }] }, LINE_COPY.neighborsOf(of === FOCUS ? "this" : of))];
  }
  m = c.match(/^(?:similar to|like) (.+)$/i);
  if (m) {
    const of = nameOf(m[1]!);
    return [makeLayer("show", "nodes", { nodes: [{ t: "about", phrase: of }] }), makeLayer("show", "nodes", { nodes: [{ t: "name", slugs: [of] }] })];
  }
  const f = filterClause(c);
  return f ? [f] : null;
}

/** Casual English as layers. `op` is the prefix the line was typed with; every operation reads the words the same way. */
export function fromSentence(text: string, op: "replace" | "stack" | "remove" = "replace"): Sentence {
  void op;
  const src = text.trim().replace(/[.!?]+$/, "").replace(/\s+/g, " ");
  const layers: Layer[] = [];
  for (const clause of src.split(/\s*[,;]\s*|\s+then\s+/i).filter(Boolean)) {
    const ls = clauseLayers(clause);
    if (!ls) return { layers: [], lines: [], unknown: text.trim() };
    layers.push(...ls);
  }
  if (!layers.length) return { layers: [], lines: [], unknown: text.trim() };
  return { layers, lines: layers.map(print) };
}
