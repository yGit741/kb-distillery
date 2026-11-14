import { flag } from "@/flags";
import { DIMENSIONS, type GraphSubject } from "./colourDimensions";
import { sourcesOf, type NeighborMap } from "./graphData";
import type { GraphSchema } from "./schema";
import { useGraphUi } from "./store";
import { effectiveColorBy, type ColorBy } from "./style";
import type { GNode } from "./types";

/**
 * The graph's two views (flag graph-intent). Concepts: the concept layer and the links among concepts, each concept
 * with a quiet count of its sources. Sources: the same concepts plus the source pages and the links between the two,
 * sources on one side. Which view is on is read from the drawn types (a source type drawn = Sources), so a saved
 * view, the types card and the `>` line all agree with the toggle, and the selection carries across.
 *
 * Health (flag knowledge-health) takes the place of Sources on the switch: the concepts alone, coloured by how many
 * sources back them. It is read from the colouring ("support") the same way, so a saved view keeps it.
 */
export interface SubjectOption {
  id: GraphSubject;
  label: string;
  hint: string;
}
export const SUBJECTS: readonly SubjectOption[] = [
  { id: "concepts", label: "Concepts", hint: "Concepts and the links between them" },
  { id: "sources", label: "Sources", hint: "Sources on the left, concepts on the right" },
];
export const HEALTH: SubjectOption = { id: "health", label: "Health", hint: "Which concepts and which kinds of source need care" };
/** The switch's two views: Concepts and Sources, or Concepts and Health under flag knowledge-health. */
export const subjectsFor = (health: boolean): readonly SubjectOption[] => (health ? [SUBJECTS[0]!, HEALTH] : SUBJECTS);

const typesOf = (schema: GraphSchema, layer: string): string[] => schema.types.filter((t) => t.layer === layer).map((t) => t.id);

/** `shownTypes === null` draws every type, sources included. */
export function subjectOf(schema: GraphSchema, shownTypes: ReadonlySet<string> | null, by?: ColorBy): GraphSubject {
  if (!shownTypes) return "sources";
  if (typesOf(schema, "source").some((t) => shownTypes.has(t))) return "sources";
  return by === "support" ? "health" : "concepts";
}

/** The types a view draws, starting from what is drawn now: the concept types the user chose stay as they are. */
export function typesFor(subject: GraphSubject, schema: GraphSchema, shownTypes: ReadonlySet<string> | null): Set<string> {
  const concepts = typesOf(schema, "concept");
  const kept = concepts.filter((t) => !shownTypes || shownTypes.has(t));
  const base = kept.length ? kept : concepts;
  return new Set(subject === "sources" ? [...base, ...typesOf(schema, "source")] : base);
}

/** The colouring a view opens with: the one in use when the view offers it, else the view's first. */
export function colourFor(subject: GraphSubject, by: ColorBy): ColorBy {
  const dims = DIMENSIONS[subject];
  return dims.some((d) => d.by === by) ? by : dims[0]!.by;
}

/** Switch the graph to a view: its types, a colouring it offers, and no colour value left hidden from the other. */
export function applySubject(subject: GraphSubject, schema: GraphSchema, shownTypes: ReadonlySet<string> | null): boolean {
  const by = effectiveColorBy(useGraphUi.getState().colorBy);
  const health = flag("knowledge-health") && flag("graph-intent");
  if (subjectOf(schema, shownTypes, health ? by : undefined) === subject) return false;
  useGraphUi.setState({ shownTypes: typesFor(subject, schema, shownTypes), colorBy: colourFor(subject, by), hiddenKeys: new Set(), story: "" });
  return true;
}

/**
 * The "support" colouring belongs to the Health view alone. A saved view or a typed shape can restore it anywhere, so
 * when it is on outside Health (the flag off, or source types drawn) this names the colouring to fall back to: the
 * first one the view on screen offers. null = the colouring may stay.
 */
export function settledColour(by: ColorBy, health: boolean, schema: GraphSchema, shownTypes: ReadonlySet<string> | null): ColorBy | null {
  if (by !== "support") return null;
  if (health && subjectOf(schema, shownTypes, by) === "health") return null;
  return colourFor(subjectOf(schema, shownTypes), by);
}

/** How many distinct source pages each concept links to (in either direction), over the whole kb. */
export function sourceCounts(nodes: readonly GNode[], neighbors: NeighborMap): Map<string, number> {
  const byId = new Map(nodes.map((n) => [n.id, n] as const));
  const out = new Map<string, number>();
  for (const n of nodes) {
    if (n.layer !== "concept") continue;
    const c = new Set(sourcesOf(n.id, neighbors, byId)).size;
    if (c) out.set(n.id, c);
  }
  return out;
}

/** The `>` line's view words ("health" only under flag knowledge-health). */
export function subjectWord(typed: string, health = false): GraphSubject | null {
  const t = typed.trim().toLowerCase().replace(/\s+view$/, "");
  return t === "concepts" || t === "sources" || (health && t === "health") ? t : null;
}

/** How far each side sits from the centre in the Sources view, in graph units. */
export const sideOffset = (linkDistance: number, drawn: number): number => Math.max(220, linkDistance * (2 + Math.sqrt(drawn) / 4));
