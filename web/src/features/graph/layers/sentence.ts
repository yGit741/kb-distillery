import { FAVORITES, FOCUS, makeLayer, type EdgeCond, type Layer, type NodeCond, type Op } from "./model";
import { print } from "./grammar";
import { algoClause } from "./algoWords";
import { LINE_COPY } from "../shell/copy";

/**
 * Casual English into layers (flag graph-intent): rules only, no model call. Text it cannot read comes back as
 * `unknown`, which the shell sends to the model (useLlmLayers). Every word it understands lives in a table below.
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
/** The legend's own names, its field names and loose words, to the colour mode they mean ("type" on the legend is the
 * page's format; colour mode "type" draws as the theme, so it is never the answer). */
const COLOR_FIELDS: Record<string, string> = {
  type: "format", types: "format", kind: "format", kinds: "format", format: "format",
  theme: "area", themes: "area", area: "area", areas: "area",
  maturity: "status", status: "status",
  "digest status": "depth", digest: "depth", depth: "depth",
  recency: "recency", recent: "recency", "date added": "added", added: "added", date: "added",
  "source count": "evidence", evidence: "evidence", "source support": "support", support: "support",
  links: "degree", connections: "degree", degree: "degree",
  score: "score", layer: "layer", none: "none",
};
/** Words the rules key on, so a small typo in one still reads ("orphnas", "colur", "theams"). Never page names. */
const VOCAB = ["orphans", "orphan", "isolated", "leaves", "favorites", "favourites", "contradictions", "colour", "color", "coloured", "colored", "theme", "themes", "maturity", "connections", "exclude"];
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
  // "hide", and the ways people say it: "exclude all orphans", "filter out hubs", "no leaves", "without favorites"
  // ("no question notes" stays the "with no … notes" condition below, never a hide)
  const HIDE = /^(?:hide|exclude|remove|drop|filter out|(?:don['’]?t|do not|never) show|(?:without|no)(?!\s+[\w-]+\s+notes?\b))\s+/i;
  if (HIDE.test(rest)) {
    kind = "hide";
    rest = rest.replace(HIDE, "");
  }
  rest = rest.replace(/^(?:only|just|show(?: me)?|find|keep)\s+/i, "");
  const work = { s: rest };

  // pages that have a link of some type: "nodes that share a contradicts edge"
  const has = rest.match(/^(?:nodes|pages)?\s*(?:that |which )?(?:share|have|has|with|having)\s+an?\s+([\w-]+)\s+(?:edge|link)s?$/i);
  if (has) return makeLayer(kind, "nodes", { nodes: [{ t: "hasEdge", type: has[1]!.toLowerCase() }] });

  // a link type is a word, never a count: "more than 5 links" counts links
  const edgeWord = rest.match(/\b([a-z][\w-]*)\s+(?:edges?|links?)\b/i);
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
  // graph-theory words first (flag graph-algos): shortest paths, components, "and their neighbours"
  const algo = algoClause(c, clauseLayers);
  if (algo !== undefined) return algo;
  let m = c.match(/^(?:colou?r)(?:ed)?(?: the)?(?: nodes| pages)? by (?:the )?([\w-]+(?: [\w-]+)?)$/i);
  if (m) {
    // the legend's name or a loose word, a small typo forgiven ("theams" -> theme); anything else is for the model
    const f = m[1]!.toLowerCase();
    const key = f in COLOR_FIELDS ? f : closest(f, Object.keys(COLOR_FIELDS));
    if (!key) return null;
    return [makeLayer("style", "nodes", {}, "", { style: { color: COLOR_FIELDS[key] as never } })];
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
  // meaning: only a quoted phrase, so ordinary sentences with the word "about" keep their old reading
  m = c.match(/^(?:show )?(?:(?:nodes|pages|notes) )?about\s+["“](.+?)["”]$/i);
  if (m) return [makeLayer("show", "nodes", { nodes: [{ t: "about", phrase: m[1]!.trim() }] })];
  const f = filterClause(c);
  return f ? [f] : null;
}

/** Edit distance (insert, delete, substitute, swap two neighbours), stopping early past `max`. */
function distance(a: string, b: string, max: number): number {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0]![j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++) {
      const sub = a[i - 1] === b[j - 1] ? 0 : 1;
      let v = Math.min(d[i - 1]![j]! + 1, d[i]![j - 1]! + 1, d[i - 1]![j - 1]! + sub);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, d[i - 2]![j - 2]! + 1);
      d[i]![j] = v;
    }
  return d[a.length]![b.length]!;
}

/** The closest of `words` to `w` within a small typo (one letter in a short word, two in a long one), else null. */
function closest(w: string, words: readonly string[]): string | null {
  const max = w.length >= 6 ? 2 : w.length >= 4 ? 1 : 0;
  if (!max) return null;
  let best: string | null = null;
  let bestD = max + 1;
  for (const k of words) {
    const dd = distance(w, k, max);
    if (dd < bestD) [best, bestD] = [k, dd];
  }
  return best;
}

/** A small typo in one of the rules' own words, put right; any other word (a page name) is left alone. */
const KNOWN = new Set([
  ...VOCAB,
  ...Object.keys(COLOR_FIELDS).flatMap((k) => k.split(" ")),
  ...Object.keys(SIZE_FIELDS),
  ...Object.keys(TYPE_WORDS),
  ...Object.keys(EDGE_WORDS),
  ...Object.keys(NUM_OPS).flatMap((k) => k.split(" ")),
  ...Object.keys(WIDTHS),
  ...STOP,
  ...["only", "hide", "show", "by", "size", "scale", "more", "than", "less", "hops", "hop", "within", "hubs", "hub", "leaf", "orphan"],
  ...["favorite", "favourite", "named", "name", "about", "text", "mentioning", "similar", "neighbours", "neighbors", "paths", "path"],
  ...["created", "added", "month", "week", "today", "days", "last", "this", "new", "dont", "don't", "never", "without", "remove", "drop", "filter"],
]);
function mendTypos(src: string): string {
  // a page name, a phrase or a quote follows these: nothing from there on is mended ("about Colorado" stays)
  const cut = src.search(/\b(?:of|to|between|like|about|named?|text|mentioning)\b|["“]/i);
  const head = cut < 0 ? src : src.slice(0, cut);
  const mended = head.replace(/[A-Za-z]+/g, (w) => {
    const lw = w.toLowerCase();
    if (KNOWN.has(lw) || lw.length < 4) return w;
    return closest(lw, VOCAB) ?? w;
  });
  return cut < 0 ? mended : mended + src.slice(cut);
}

/** Where one clause ends and the next begins: a comma or "then", and also before a style ("only orphans colour by
 * theme") or a second verb ("only papers and hide people"), so a line reads without commas. */
const CLAUSE_BREAK = /\s*[,;]\s*|\s+then\s+|\s+(?:and\s+)?(?=(?:colou?r(?:ed)?|size|scale)\s+(?:the\s+)?(?:nodes\s+|pages\s+)?by\b)|\s+and\s+(?=(?:hide|show|only|exclude|don['’]?t show)\b)/i;

/** Casual English as layers. `op` is the prefix the line was typed with; every operation reads the words the same way. */
export function fromSentence(text: string, op: "replace" | "stack" | "remove" = "replace"): Sentence {
  void op;
  const src = mendTypos(text.trim().replace(/[.!?]+$/, "").replace(/\s+/g, " "));
  const layers: Layer[] = [];
  for (const clause of src.split(CLAUSE_BREAK).filter(Boolean)) {
    const ls = clauseLayers(clause);
    if (!ls) return { layers: [], lines: [], unknown: text.trim() };
    layers.push(...ls);
  }
  if (!layers.length) return { layers: [], lines: [], unknown: text.trim() };
  return { layers, lines: layers.map(print) };
}
