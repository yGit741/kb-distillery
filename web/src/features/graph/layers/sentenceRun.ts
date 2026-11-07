import type { GNode } from "../types";
import { LINE_COPY } from "../shell/copy";
import { resolveNames, type Ambiguity } from "./names";
import type { Layer } from "./model";
import { fromSentence } from "./sentence";

/** What a `>` sentence comes to once read and its names looked up. */
export type Plan =
  | { kind: "unknown" }
  | { kind: "ready"; layers: Layer[] }
  /** A name that needs the user: `pick` lists its options; `chosen` holds the names already picked. */
  | { kind: "ask"; pick: Ambiguity; chosen: Record<string, string> }
  /** A name no page matches. */
  | { kind: "missing"; name: string };

/** Chip words: a lone layer keeps the sentence as typed, several layers each keep their own line. */
const withText = (layers: Layer[], lines: string[], typed: string): Layer[] => layers.map((l, i) => ({ ...l, text: layers.length === 1 ? typed : lines[i]! }));

export function planSentence(typed: string, nodes: readonly GNode[], opts: { focus?: string; chosen?: Record<string, string> } = {}): Plan {
  const s = fromSentence(typed);
  if (s.unknown !== undefined) return { kind: "unknown" };
  return planLayers(s.layers, s.lines, typed, nodes, opts);
}

/** Layers already read (by the rules or by the model): look their names up and say what comes of it. */
export function planLayers(layers: Layer[], lines: string[], typed: string, nodes: readonly GNode[], opts: { focus?: string; chosen?: Record<string, string> } = {}): Plan {
  const r = resolveNames(withText(layers, lines, typed), nodes, opts);
  const gap = r.ambiguous.find((a) => a.options.length === 0);
  if (gap) return { kind: "missing", name: gap.name };
  const first = r.ambiguous[0];
  if (first) return { kind: "ask", pick: first, chosen: opts.chosen ?? {} };
  return { kind: "ready", layers: r.layers };
}

export const missingNote = (name: string) => LINE_COPY.noSuchPage(name);
