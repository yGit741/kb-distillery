import { flag } from "@/flags";
import { FOCUS, makeLayer, type Layer } from "./model";

/**
 * Graph-theory words in a `>` line (flag graph-algos), read before the other rules:
 *  - "shortest path between A and B" / "from A to B", "all shortest paths between A and B"
 *  - "common neighbours of A and B"
 *  - "largest component", "component of A"
 *  - "<clause> and their neighbours", "<clause> +2 hops": the clause's pages and the pages that many links away
 *  - "deg>4", "deg >= 4": degree
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

  // "deg>4": the rules read "degree > 4"
  if (/\bdeg\b\s*(?:[<>=]|>=|<=)/i.test(c)) return read(deg(c));
  return undefined;
}

/** "deg>4" as "degree > 4". */
const deg = (s: string) => s.replace(/\bdeg\b\s*(>=|<=|>|<|=)\s*/gi, "degree $1 ");
