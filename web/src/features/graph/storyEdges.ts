import type { Story } from "./lab/views";
import type { GLink, GNode, GRelation } from "./types";

/**
 * The model a view draws. A view that names relation kinds (`edges`, e.g. Citations: `cites`) draws those relations
 * as its links, in place of the page links, and its pages' in/out degrees count those links (so size, labels and
 * the Connected filter rank by citations); every other view draws the model as it is. Only links and degrees
 * change, so the legend, hover and the inspector work as on any view.
 */
export function withStoryEdges<M extends { nodes: readonly GNode[]; links: readonly GLink[]; relations?: readonly GRelation[] }>(
  model: M,
  story: Pick<Story, "edges"> | undefined,
): M {
  const kinds = story?.edges;
  if (!kinds?.length) return model;
  const want = new Set(kinds);
  const ids = new Set(model.nodes.map((n) => n.id));
  const links: GLink[] = (model.relations ?? [])
    .filter((r) => want.has(r.kind) && ids.has(r.source) && ids.has(r.target))
    .map((r) => ({ source: r.source, target: r.target, kind: r.kind === "cites" ? "cites" : "related" }));
  const out = new Map<string, number>();
  const into = new Map<string, number>();
  for (const l of links) {
    out.set(l.source, (out.get(l.source) ?? 0) + 1);
    into.set(l.target, (into.get(l.target) ?? 0) + 1);
  }
  const nodes = model.nodes.map((n) => ({ ...n, inDegree: into.get(n.id) ?? 0, outDegree: out.get(n.id) ?? 0 }));
  return { ...model, nodes, links };
}

/**
 * The edge view that is really on screen: the one the store names, while the types drawn are still the view's own.
 * A saved preference or a switch of what the graph shows can leave `edgeStory` behind with other types drawn (the
 * Concepts view carrying Citations' empty `cites` links); then the page links are drawn as on any view.
 */
export function liveEdgeStory(id: string, shownTypes: ReadonlySet<string> | null | undefined, find: (id: string) => Pick<Story, "edges" | "types"> | undefined): string {
  const st = id ? find(id) : undefined;
  if (!st?.edges?.length) return "";
  if (!st.types?.length) return id;
  // null = every type is drawn (the view's own included)
  if (shownTypes === null) return id;
  return shownTypes && st.types.every((t) => shownTypes.has(t)) ? id : "";
}
