import { flag } from "@/flags";
import { fromSentence } from "../layers/sentence";

/**
 * View suggestions for a plain line (flag graph-intent): a word about the graph's shape ("orp", "hubs", "edges",
 * "colour") offers ready `>` lines, and a whole line the rules can read as a view change is offered as one. Pure:
 * the panel turns each suggestion into a row that previews it.
 */
export interface ViewSuggestion {
  /** The sentence, without the `>`. */
  line: string;
  hint: string;
  /** The whole typed line, read as a view change (not a ready line). */
  whole?: boolean;
  /** The start of a line that needs page names ("shortest path between "): the row puts it in the line, where the
   * names complete, and runs nothing. */
  fill?: boolean;
}

interface Group {
  /** Words that call the group, typed whole (or plural). */
  keys: string[];
  /** A word typed as the start of a stem calls the group from this many letters on (0: whole words only). */
  prefix: number;
  /** The words a prefix may complete ("orp" -> orphan); never the rarer keys ("iso" is not "isolated"). */
  stems?: string[];
  lines: (kinds: readonly string[]) => ViewSuggestion[];
  /** Its words can be ordinary search words too ("core", "path", "important"): its rows follow the page results and
   * never take Enter. */
  follow?: boolean;
}

const GROUPS: Group[] = [
  {
    keys: ["orphan", "orphans", "isolated", "unlinked"],
    prefix: 3,
    stems: ["orphan"],
    lines: () => [
      { line: "only orphans", hint: "pages with no links" },
      { line: "don't show orphans", hint: "hide pages with no links" },
    ],
  },
  {
    keys: ["hub", "hubs"],
    prefix: 0,
    lines: () => [
      { line: "only hubs", hint: "pages with 8 or more links" },
      { line: "don't show hubs", hint: "hide the busiest pages" },
    ],
  },
  {
    keys: ["leaf", "leaves"],
    prefix: 0,
    lines: () => [
      { line: "only leaves", hint: "pages with one link" },
      { line: "don't show leaves", hint: "hide pages with one link" },
    ],
  },
  {
    keys: ["node", "nodes", "degree", "connections", "connected", "link", "links"],
    prefix: 0,
    lines: () => [
      { line: "pages with more than 5 links", hint: "filter by links" },
      { line: "only hubs", hint: "pages with 8 or more links" },
    ],
  },
  {
    keys: ["edge", "edges"],
    prefix: 3,
    stems: ["edge"],
    lines: (kinds) => kinds.slice(0, 2).flatMap((k) => [
      { line: `only ${k} edges`, hint: `${k} links only` },
      { line: `hide ${k} edges`, hint: `hide ${k} links` },
    ]),
  },
  {
    keys: ["colour", "color", "colours", "colors", "coloured", "colored"],
    prefix: 4,
    stems: ["colour", "color"],
    lines: () => [
      { line: "colour by maturity", hint: "style" },
      { line: "colour by area", hint: "style" },
    ],
  },
  {
    keys: ["size", "sized", "bigger"],
    prefix: 0,
    lines: () => [{ line: "size by links", hint: "style" }],
  },
];

/** Flag graph-algos: graph-theory words call the graph-theory lines. */
const ALGO_GROUPS: Group[] = [
  {
    keys: ["community", "communities", "cluster", "clusters"],
    prefix: 5,
    stems: ["community", "communities", "cluster"],
    follow: true,
    lines: () => [
      { line: "colour by community", hint: "groups of closely linked pages" },
      { line: "largest community", hint: "the biggest group" },
    ],
  },
  {
    keys: ["central", "centrality", "betweenness", "pagerank", "important", "influential"],
    prefix: 5,
    stems: ["central", "centrality", "betweenness", "pagerank"],
    follow: true,
    lines: () => [
      { line: "top 10 by betweenness", hint: "pages that bridge the most" },
      { line: "top 10 by pagerank", hint: "pages the links point to most" },
    ],
  },
  {
    keys: ["bridge", "cut", "articulation", "bottleneck"],
    prefix: 0,
    follow: true,
    lines: () => [
      { line: "cut vertices", hint: "pages whose removal splits the graph" },
      { line: "bridges", hint: "links whose removal splits the graph" },
    ],
  },
  {
    keys: ["clique", "triangle"],
    prefix: 4,
    stems: ["clique", "triangle"],
    follow: true,
    lines: () => [
      { line: "cliques of 4+", hint: "pages all linked to each other" },
      { line: "triangles", hint: "cliques of three" },
    ],
  },
  { keys: ["core", "kcore", "k-core"], prefix: 0, follow: true, lines: () => [{ line: "the 3-core", hint: "the dense centre" }] },
  {
    keys: ["component", "island"],
    prefix: 5,
    stems: ["component"],
    follow: true,
    lines: () => [
      { line: "largest component", hint: "the biggest connected part" },
      { line: "colour by component", hint: "each connected part its own colour" },
    ],
  },
  { keys: ["path", "shortest", "route"], prefix: 0, follow: true, lines: () => [{ line: "shortest path between ", hint: "then type two page names", fill: true }] },
  {
    keys: ["neighbour", "neighbor", "neighbourhood", "neighborhood", "near", "ego"],
    prefix: 0,
    follow: true,
    lines: () => [{ line: "near ", hint: "a page and its neighbours: type its name", fill: true }],
  },
];

/** A view line whose conditions go past a page type or a name: worth offering for the whole typed line. */
const SHAPE_WORDS = /\b(?:degree|edges|style|hops|favorite)\b/;
const ALGO_SHAPE_WORDS = /\b(?:degree|edges|style|hops?|favorite|shortest|common neighbours|component|clique|core|cut vertex|bridge end|top \d+ by|community|expand)\b/;
const MAX = 5;
/** A search of more words than this is a search: a shape word in it calls nothing (only a whole-line read does). */
const SHORT = 2;

const calls = (g: Group, word: string, last: boolean): boolean =>
  g.keys.some((k) => word === k || word === `${k}s`) || (g.prefix > 0 && last && word.length >= g.prefix && (g.stems ?? []).some((st) => st.startsWith(word)));

export interface ViewSuggestions {
  rows: ViewSuggestion[];
  /** The line clearly means the view (it reads as one, or it is one shape word): the rows go first and take Enter.
   * Otherwise they follow the page results, and Enter keeps doing what it did. */
  first: boolean;
}

/**
 * Suggestions for `text`, at most five. `kinds` are the link kinds the graph has, so an edge suggestion never names
 * a kind with no link; a kind typed by name ("related edges") comes first. A shape word calls its lines only in a
 * short line (two words at most, the shape word first or last): "edge computing" and "graph link prediction" stay
 * searches.
 */
export function suggestViews(text: string, kinds: readonly string[] = []): ViewSuggestions {
  const none = { rows: [], first: false };
  const t = text.trim().toLowerCase();
  if (!t || t.startsWith(">") || t.startsWith("/")) return none;
  const out: ViewSuggestion[] = [];
  const words = t.split(/[^a-z']+/).filter(Boolean);
  // a sentence (two words or more; one word is covered by the ready lines) the rules read as a view change
  const read = words.length > 1 ? fromSentence(t) : null;
  const algos = flag("graph-algos");
  // the words of the language only, not a quoted page name ("about "community detection"" is no community view)
  const said = read ? read.lines.join(" ").replace(/"(?:[^"\\]|\\.)*"/g, "") : "";
  const whole = !!read && read.unknown === undefined && read.layers.length > 0 && (algos ? ALGO_SHAPE_WORDS : SHAPE_WORDS).test(said);
  if (whole) out.push({ line: text.trim(), hint: read!.lines.join(" · "), whole: true });
  const short = words.length <= SHORT;
  const edges = (w: string) => w === "edge" || w === "edges";
  // a link kind typed by name next to an edge word ("related edges") offers that kind first
  const named = short && words.some(edges) ? kinds.filter((k) => words.includes(k)) : [];
  const order = [...named, ...kinds.filter((k) => !named.includes(k))];
  let hits = 0;
  if (short)
    for (const g of algos ? [...GROUPS, ...ALGO_GROUPS] : GROUPS) {
      const ends = [words[0]!, words[words.length - 1]!];
      const hit = ends.some((w, i) => calls(g, w, i === 1 || words.length === 1)) || (g.keys.includes("edge") && named.length > 0 && words.every((w) => edges(w) || named.includes(w)));
      if (hit) {
        if (!g.follow) hits++;
        out.push(...g.lines(order));
      }
    }
  const seen = new Set<string>();
  const rows = out.filter((s) => (seen.has(s.line.toLowerCase()) ? false : (seen.add(s.line.toLowerCase()), true))).slice(0, MAX);
  return { rows, first: whole || (words.length === 1 && hits > 0) };
}
