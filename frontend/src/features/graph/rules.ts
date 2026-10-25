import type { GNode } from "./types";

export type RuleOp = "is" | "is-not" | "contains" | "not-contains" | "gte" | "lte";
export type RuleField = "type" | "layer" | "depth" | "status" | "area" | "year" | "slug" | "title" | "inDegree" | "outDegree";

export interface Rule {
  mode: "include" | "exclude";
  field: RuleField;
  op: RuleOp;
  value: string;
}

export const RULE_FIELDS: readonly { id: RuleField; label: string; ops: readonly RuleOp[] }[] = [
  { id: "type", label: "Type", ops: ["is", "is-not"] },
  { id: "layer", label: "Layer", ops: ["is", "is-not"] },
  { id: "depth", label: "Depth", ops: ["is", "is-not"] },
  { id: "status", label: "Status", ops: ["is", "is-not"] },
  { id: "area", label: "Area", ops: ["contains", "not-contains"] },
  { id: "year", label: "Year", ops: ["is", "gte", "lte"] },
  { id: "slug", label: "Slug", ops: ["contains", "not-contains"] },
  { id: "title", label: "Title", ops: ["contains", "not-contains"] },
  { id: "inDegree", label: "In-links", ops: ["gte", "lte"] },
  { id: "outDegree", label: "Out-links", ops: ["gte", "lte"] },
];

const NUMERIC: readonly RuleField[] = ["inDegree", "outDegree", "year"];

export const fieldOps = (field: RuleField): readonly RuleOp[] => RULE_FIELDS.find((f) => f.id === field)?.ops ?? ["is"];

export const newRule = (): Rule => ({ mode: "include", field: "type", op: "is", value: "" });

function actualOf(node: GNode, field: RuleField): unknown {
  switch (field) {
    case "area":
      return (node.areas || []).join(" ");
    case "slug":
      return node.id;
    case "title":
      return node.title || "";
    case "year":
      return node.year;
    default:
      return node[field];
  }
}

/** One filter row against one node. An empty value matches everything (except the numeric fields). */
export function matchRule(node: GNode, rule: Rule): boolean {
  const { field, op, value } = rule;
  if (!value && !NUMERIC.includes(field)) return true;
  const actual = String(actualOf(node, field) ?? "").toLowerCase();
  const val = value.toLowerCase();
  let ok: boolean;
  switch (op) {
    case "is":
      ok = actual === val;
      break;
    case "is-not":
      ok = actual !== val;
      break;
    case "contains":
      ok = actual.includes(val);
      break;
    case "not-contains":
      ok = !actual.includes(val);
      break;
    case "gte":
      ok = Number(actualOf(node, field) ?? 0) >= Number(value);
      break;
    case "lte":
      ok = Number(actualOf(node, field) ?? 0) <= Number(value);
      break;
    default:
      ok = true;
  }
  return rule.mode === "exclude" ? !ok : ok;
}

export interface VisibilityOptions {
  /** Types drawn at all; null = every type. */
  shownTypes: ReadonlySet<string> | null;
  /** Source depths drawn; null = all. Pages that carry no depth are not affected. */
  shownDepths: ReadonlySet<string> | null;
  search: string;
  rules: readonly Rule[];
  /** A view (search, picked pages, scope): only these ids survive the other filters... */
  restrict: ReadonlySet<string> | null;
  /** ...unless `force`: then they are drawn whatever else hides them. */
  force: boolean;
  /** Sources revealed by "See sources (N)", drawn whatever the type filter says. */
  revealed: ReadonlySet<string>;
  /** A view's own rule on top of the filters (./publicPredicate); null = none. */
  keep?: ((n: GNode) => boolean) | null;
}

export function passesText(node: GNode, search: string): boolean {
  const q = search.trim().toLowerCase();
  if (!q) return true;
  return `${node.id} ${node.title || ""}`.toLowerCase().includes(q);
}

export const typeShown = (type: string, shown: ReadonlySet<string> | null): boolean => !shown || shown.has(type || "unknown");

/** The ids drawn: type and depth filters, text, rules, then the view and revealed sources on top. */
export function computeVisible(nodes: readonly GNode[], o: VisibilityOptions): Set<string> {
  const out = new Set<string>();
  const ids = new Set<string>();
  for (const n of nodes) {
    ids.add(n.id);
    if (!typeShown(n.type, o.shownTypes)) continue;
    if (o.shownDepths && n.layer === "source" && n.depth && !o.shownDepths.has(n.depth)) continue;
    if (o.keep && !o.keep(n)) continue;
    if (o.restrict && !o.restrict.has(n.id)) continue;
    if (!passesText(n, o.search)) continue;
    if (o.rules.every((r) => matchRule(n, r))) out.add(n.id);
  }
  for (const id of o.revealed) if (ids.has(id)) out.add(id);
  if (o.force && o.restrict) for (const id of o.restrict) if (ids.has(id)) out.add(id);
  return out;
}
