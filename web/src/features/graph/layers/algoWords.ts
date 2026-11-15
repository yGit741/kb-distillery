import { flag } from "@/flags";
import { FOCUS, makeLayer, type Layer, type NodeCond } from "./model";

/**
 * Graph-theory words in a `>` line (flag graph-algos), read before the other rules:
 *  - "shortest path between A and B" / "from A to B", "all shortest paths between A and B"
 *  - "common neighbours of A and B"
 *  - "largest component", "component of A"
 *  - "<clause> and their neighbours", "<clause> +2 hops": the clause's pages and the pages that many links away
 *  - "deg>4", "deg >= 4": degree
 *  - "cliques of 4+", "triangles", "the 3-core", "cut vertices", "bridges", "top 20 by betweenness", "most central",
 *    "largest community", "community of A", "colour by community" / "communities", "colour by component"
 *  - "near A", "close to A", "around A": A and its neighbours
 * Returns undefined when the clause is not one of these (the other rules read it), null when it is but cannot be read.
 */
type Read = (clause: string) => Layer[] | null;

const unq = (s: string) => s.trim().replace(/^["'“‘]+|["'”’]+$/g, "").trim();
const nameOf = (s: string): string => (/^(?:this|this page|here)$/i.test(unq(s)) ? FOCUS : unq(s));

export function algoClause(clause: string, read: Read): Layer[] | null | undefined {
  if (!flag("graph-algos")) return undefined;
  const c = clause.trim();
  // "and their neighbours" / "+2 hops" first: the clause before it, grown ("shortest path from A to D and their
  // neighbours" grows the path)
  let m =
    c.match(/^(.+?)\s+(?:and|with|plus|\+)\s+(?:their|its|the|all)?\s*(?:(\d+)[- ]hops? )?neighbou?rs?(?:hood)?$/i) ??
    c.match(/^(.+?)\s*(?:\+|and|plus)\s*(\d+)\s*hops?(?: around)?$/i);
  if (m) {
    const inner = read(deg(m[1]!));
    if (!inner || inner.length !== 1 || inner[0]!.target !== "nodes" || inner[0]!.kind === "style") return null;
    return [{ ...inner[0]!, expand: m[2] ? Number(m[2]) : 1 }];
  }
  m = c.match(/^(?:show |find |draw )?(?:me )?(?:the |a )?(all )?shortest paths? (?:between|from) (.+?) (?:and|to) (.+)$/i);
  if (m) return [makeLayer("show", "nodes", { nodes: [{ t: "shortest", a: nameOf(m[2]!), b: nameOf(m[3]!), ...(m[1] ? { all: true } : {}) }] })];
  m = c.match(/^(?:show |find )?(?:me )?(?:the )?(?:common|shared|mutual) neighbou?rs (?:of|between) (.+?) and (.+)$/i);
  if (m) return [makeLayer("show", "nodes", { nodes: [{ t: "common", a: nameOf(m[1]!), b: nameOf(m[2]!) }] })];
  m = c.match(/^(?:show |only )?(?:me )?(?:the )?(?:largest|biggest|main|giant) (?:connected )?component$/i);
  if (m) return [makeLayer("show", "nodes", { nodes: [{ t: "component", rank: 1 }] })];
  m = c.match(/^(?:show |only )?(?:me )?(?:the )?(?:connected )?component (?:of|with|containing|around) (.+)$/i);
  if (m) return [makeLayer("show", "nodes", { nodes: [{ t: "component", of: nameOf(m[1]!) }] })];
  const show = (cond: NodeCond) => [makeLayer("show", "nodes", { nodes: [cond] })];
  const lead = "^(?:show |only |find )?(?:me )?(?:the )?(?:pages )?(?:in )?(?:a |the )?";
  m = c.match(new RegExp(`${lead}(?:cliques?|triangles?)(?: (?:of|with) (?:size )?(\\d+)\\+?(?: or more| pages)?| ?(?:>=|of at least) ?(\\d+))?$`, "i"));
  if (m) return show({ t: "clique", min: Math.max(2, Number(m[1] ?? m[2] ?? 3)) });
  m = c.match(new RegExp(`${lead}(?:(\\d+)[- ]?core|k-?core (\\d+)|core (\\d+))$`, "i"));
  if (m) return show({ t: "core", k: Math.max(1, Number(m[1] ?? m[2] ?? m[3])) });
  if (new RegExp(`${lead}(?:cut (?:vertices|vertexes|vertex|points?|nodes|pages)|articulation (?:points?|nodes|pages))$`, "i").test(c)) return show({ t: "cut" });
  if (new RegExp(`${lead}bridges?(?: ends?| pages| nodes)?$`, "i").test(c)) return show({ t: "bridge" });
  m = c.match(new RegExp(`${lead}(?:top|most central)(?: (\\d+))?(?: pages| nodes)?(?: (?:by|in|on) (betweenness|page ?rank|degree|closeness|centrality))?$`, "i"));
  if (m && (m[2] || /most central/i.test(c))) {
    const w = (m[2] ?? "betweenness").toLowerCase().replace(" ", "");
    const by = w === "centrality" ? "betweenness" : (w as "betweenness" | "pagerank" | "degree" | "closeness");
    return show({ t: "top", by, n: Math.max(1, Number(m[1] ?? 20)) });
  }
  m = c.match(new RegExp(`${lead}(?:largest|biggest|main) (?:community|cluster)$`, "i"));
  if (m) return show({ t: "community", rank: 1 });
  m = c.match(new RegExp(`${lead}(?:community|cluster) (?:of|with|containing|around) (.+)$`, "i"));
  if (m) return show({ t: "community", of: nameOf(m[1]!) });
  // "near A", "close to A", "around A": A and the pages one link from it
  m = c.match(/^(?:show |find )?(?:me )?(?:all )?(?:the )?(?:pages |nodes |everything )?(?:that are |which are )?(?:near|close to|next to|around) (.+)$/i);
  if (m) return show({ t: "hops", of: nameOf(m[1]!), n: 1 });
  // colour by the structure: communities, clusters, components
  m = c.match(/^(?:colou?r(?:ed)?(?: the)?(?: nodes| pages)? by (?:the )?)?(communit(?:y|ies)|clusters?|components?)$/i);
  if (m) return [makeLayer("style", "nodes", {}, "", { style: { color: /^comp/i.test(m[1]!) ? "component" : "community" } })];

  // "deg>4": the rules read "degree > 4"
  if (/\bdeg\b\s*(?:[<>=]|>=|<=)/i.test(c)) return read(deg(c));
  return undefined;
}

/** "deg>4" as "degree > 4". */
const deg = (s: string) => s.replace(/\bdeg\b\s*(>=|<=|>|<|=)\s*/gi, "degree $1 ");
