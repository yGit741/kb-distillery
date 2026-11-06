import { FAVORITES, FOCUS, newLayerId, type EdgeCond, type Layer, type LayerStyle, type NodeCond, type Op, type Subgraph } from "./model";

/**
 * The readable query language (flag graph-intent): one line per layer, each line maps 1:1 to a Layer.
 *
 *   show|hide nodes|edges <condition> [and <condition> ...]
 *   style nodes|edges color|size|width|label by <field or value> [for <condition> [and ...]]
 *
 * The conditions are data: one table per target, each row holding the pattern that reads a condition and the words
 * that write it, so `parse` and `print` are inverses by construction. Names are quoted; `favorites` and `this` stand
 * for the favorites and the page in focus.
 */

export interface ParseError {
  error: string;
  /** Offset into the line where reading stopped. */
  at: number;
}

export const isParseError = (x: unknown): x is ParseError => !!x && typeof x === "object" && "error" in x && "at" in x;

// ---- words
const STR = '"((?:[^"\\\\]|\\\\.)*)"';
const OPS = ">=|<=|>|<|=";
const WORD = "[\\w-]+";
const quote = (s: string) => `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
const unquote = (s: string) => s.replace(/\\(.)/g, "$1");
const strings = (s: string): string[] => [...s.matchAll(new RegExp(STR, "g"))].map((m) => unquote(m[1]!));

const ofWord = (of: string) => (of === FAVORITES ? "favorites" : of === FOCUS ? "this" : quote(of));
const ofValue = (w: string, q?: string) => (q !== undefined ? unquote(q) : w === "favorites" ? FAVORITES : FOCUS);

interface Spec<C> {
  re: RegExp;
  read: (m: RegExpMatchArray) => C;
  /** Returns null when the spec does not write this condition. */
  write: (c: C) => string | null;
}

export const NODE_SPECS: Spec<NodeCond>[] = [
  { re: /^all$/, read: () => ({ t: "all" }), write: (c) => (c.t === "all" ? "all" : null) },
  {
    re: new RegExp(`^type (${WORD}(?: or ${WORD})*)$`),
    read: (m) => {
      const v = m[1]!.split(" or ");
      return { t: "type", value: v.length === 1 ? v[0]! : v };
    },
    write: (c) => (c.t === "type" ? `type ${Array.isArray(c.value) ? c.value.join(" or ") : c.value}` : null),
  },
  { re: new RegExp(`^degree (${OPS}) (\\d+)$`), read: (m) => ({ t: "degree", op: m[1] as Op, n: Number(m[2]) }), write: (c) => (c.t === "degree" ? `degree ${c.op} ${c.n}` : null) },
  {
    re: new RegExp(`^within (\\d+) hops? of (?:${STR}|(favorites|this))$`),
    read: (m) => ({ t: "hops", n: Number(m[1]), of: ofValue(m[3]!, m[2]) }),
    write: (c) => (c.t === "hops" ? `within ${c.n} hops of ${ofWord(c.of)}` : null),
  },
  {
    re: new RegExp(`^paths between ${STR} and ${STR} up to (\\d+) hops?$`),
    read: (m) => ({ t: "paths", a: unquote(m[1]!), b: unquote(m[2]!), n: Number(m[3]) }),
    write: (c) => (c.t === "paths" ? `paths between ${quote(c.a)} and ${quote(c.b)} up to ${c.n} hops` : null),
  },
  {
    re: new RegExp(`^having edge (${WORD})( exists = false)?$`),
    read: (m) => (m[2] ? { t: "hasEdge", type: m[1]!, exists: false } : { t: "hasEdge", type: m[1]! }),
    write: (c) => (c.t === "hasEdge" ? `having edge ${c.type}${c.exists === false ? " exists = false" : ""}` : null),
  },
  { re: new RegExp(`^linked_from type (${WORD})$`), read: (m) => ({ t: "linkedFromType", type: m[1]! }), write: (c) => (c.t === "linkedFromType" ? `linked_from type ${c.type}` : null) },
  { re: /^created > (\d+)d$/, read: (m) => ({ t: "createdWithin", days: Number(m[1]) }), write: (c) => (c.t === "createdWithin" ? `created > ${c.days}d` : null) },
  { re: new RegExp(`^in area ${STR}$`), read: (m) => ({ t: "inArea", area: unquote(m[1]!) }), write: (c) => (c.t === "inArea" ? `in area ${quote(c.area)}` : null) },
  { re: new RegExp(`^about ${STR}$`), read: (m) => ({ t: "about", phrase: unquote(m[1]!) }), write: (c) => (c.t === "about" ? `about ${quote(c.phrase)}` : null) },
  { re: /^favorite$/, read: () => ({ t: "favorite" }), write: (c) => (c.t === "favorite" ? "favorite" : null) },
  { re: new RegExp(`^mentioned_in chat ${STR}$`), read: (m) => ({ t: "mentionedIn", chat: unquote(m[1]!) }), write: (c) => (c.t === "mentionedIn" ? `mentioned_in chat ${quote(c.chat)}` : null) },
  { re: new RegExp(`^text ${STR}$`), read: (m) => ({ t: "text", phrase: unquote(m[1]!) }), write: (c) => (c.t === "text" ? `text ${quote(c.phrase)}` : null) },
  {
    re: new RegExp(`^name ${STR}(?: or ${STR})*$`),
    read: (m) => ({ t: "name", slugs: strings(m[0]!) }),
    write: (c) => (c.t === "name" ? `name ${c.slugs.map(quote).join(" or ")}` : null),
  },
];

export const EDGE_SPECS: Spec<EdgeCond>[] = [
  { re: /^all$/, read: () => ({ t: "all" }), write: (c) => (c.t === "all" ? "all" : null) },
  { re: new RegExp(`^type (${WORD})$`), read: (m) => ({ t: "type", value: m[1]! }), write: (c) => (c.t === "type" ? `type ${c.value}` : null) },
  { re: new RegExp(`^count (${OPS}) (\\d+)$`), read: (m) => ({ t: "count", op: m[1] as Op, n: Number(m[2]) }), write: (c) => (c.t === "count" ? `count ${c.op} ${c.n}` : null) },
  { re: /^direction (in|out|both)$/, read: (m) => ({ t: "direction", value: m[1] as "in" | "out" | "both" }), write: (c) => (c.t === "direction" ? `direction ${c.value}` : null) },
  {
    re: new RegExp(`^between ${STR}(?: and ${STR})+$`),
    read: (m) => ({ t: "endpoints", slugs: strings(m[0]!) }),
    write: (c) => (c.t === "endpoints" ? `between ${c.slugs.map(quote).join(" and ")}` : null),
  },
];

// ---- print
function printConds<C>(specs: Spec<C>[], conds: C[] | undefined): string {
  return (conds ?? [])
    .map((c) => {
      if ((c as { t: string }).t === "not") return `not ${printConds(specs, [(c as { cond: C }).cond])}`;
      for (const s of specs) {
        const w = s.write(c);
        if (w !== null) return w;
      }
      return "";
    })
    .filter(Boolean)
    .join(" and ");
}

const styleWord = (v: unknown) => (typeof v === "string" ? v : v && typeof v === "object" && "by" in v ? String((v as { by: string }).by) : "");
const STYLE_PROPS = ["color", "size", "width", "label"] as const;

/** The layer as one line of the language. */
export function print(layer: Layer): string {
  const target = layer.target;
  const conds = target === "nodes" ? printConds(NODE_SPECS, layer.subgraph.nodes) : printConds(EDGE_SPECS, layer.subgraph.edges);
  if (layer.kind !== "style") return [layer.kind, target, conds].filter(Boolean).join(" ");
  const s = layer.style ?? {};
  const prop = STYLE_PROPS.find((p) => s[p] !== undefined) ?? "color";
  return [`style ${target} ${prop} by ${styleWord(s[prop])}`, conds && `for ${conds}`].filter(Boolean).join(" ");
}

// ---- parse
/** Split on `and` only where a condition starts, so `paths between "A" and "B"` stays whole. */
const COND_START = /^(?:not |all\b|type |degree |within |paths |having |linked_from |created |in area |about |favorite\b|mentioned_in |text |name |count |direction |between )/;

function splitConds(s: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inStr = false;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i]!;
    if (inStr) {
      cur += ch;
      if (ch === "\\" && i + 1 < s.length) cur += s[++i];
      else if (ch === '"') inStr = false;
    } else if (ch === '"') {
      inStr = true;
      cur += ch;
    } else if (s.startsWith(" and ", i) && COND_START.test(s.slice(i + 5))) {
      out.push(cur);
      cur = "";
      i += 4;
    } else cur += ch;
  }
  out.push(cur);
  return out;
}

function readCond<C>(specs: Spec<C>[], text: string, at: number): C | ParseError {
  const t = text.trim();
  if (t.startsWith("not ") && specs === (NODE_SPECS as unknown)) {
    const inner = readCond(specs, t.slice(4), at + 4);
    return isParseError(inner) ? inner : ({ t: "not", cond: inner } as unknown as C);
  }
  for (const s of specs) {
    const m = t.match(s.re);
    if (m) return s.read(m);
  }
  return { error: `cannot read "${t}"`, at };
}

function readConds<C>(specs: Spec<C>[], s: string, at: number): C[] | ParseError {
  const out: C[] = [];
  let off = at;
  for (const piece of splitConds(s)) {
    const c = readCond(specs, piece, off);
    if (isParseError(c)) return c;
    out.push(c);
    off += piece.length + 5;
  }
  return out;
}

const COLORS = new Set(["type", "layer", "depth", "status", "area", "degree", "evidence", "score", "none"]);
const SIZES = new Set(["connections", "in", "out", "uniform", "tier", "evidence", "score", "gap", "logdeg"]);
const WIDTHS = new Set(["thin", "normal", "thick"]);

function readStyle(prop: (typeof STYLE_PROPS)[number], v: string): LayerStyle {
  if (prop === "label") return { label: v };
  const known = prop === "color" ? COLORS : prop === "size" ? SIZES : WIDTHS;
  const value = known.has(v) ? v : { by: v };
  return { [prop]: value } as LayerStyle;
}

function readSubgraph(target: "nodes" | "edges", text: string | undefined, at: number): Subgraph | ParseError {
  if (!text) return {};
  if (target === "nodes") {
    const c = readConds(NODE_SPECS, text, at);
    return isParseError(c) ? c : { nodes: c };
  }
  const c = readConds(EDGE_SPECS, text, at);
  return isParseError(c) ? c : { edges: c };
}

/** One line of the language as a layer (a fresh id, no chip text), or the reason it cannot be read. */
export function parse(line: string): Layer | ParseError {
  const src = line.trim();
  const head = src.match(/^(show|hide) (nodes|edges)(?: (.*))?$/);
  if (head) {
    const target = head[2] as "nodes" | "edges";
    const at = src.length - (head[3]?.length ?? 0);
    const subgraph = readSubgraph(target, head[3], at);
    if (isParseError(subgraph)) return subgraph;
    return { id: newLayerId(), kind: head[1] as "show" | "hide", target, subgraph, text: "" };
  }
  const st = src.match(new RegExp(`^style (nodes|edges) (color|size|width|label) by (${WORD})(?: for (.*))?$`));
  if (st) {
    const target = st[1] as "nodes" | "edges";
    const at = src.length - (st[4]?.length ?? 0);
    const subgraph = readSubgraph(target, st[4], at);
    if (isParseError(subgraph)) return subgraph;
    return { id: newLayerId(), kind: "style", target, subgraph, style: readStyle(st[2] as (typeof STYLE_PROPS)[number], st[3]!), text: "" };
  }
  return { error: 'a line starts with show, hide or style, then nodes or edges', at: 0 };
}
