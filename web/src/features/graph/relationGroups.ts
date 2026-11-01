import type { GNode, GRelation } from "./types";

/** Each page id → the relations it takes part in (either end). Built once per model. */
export function relationIndex(relations: readonly GRelation[]): ReadonlyMap<string, readonly GRelation[]> {
  const out = new Map<string, GRelation[]>();
  const put = (id: string, r: GRelation) => {
    const list = out.get(id);
    if (list) list.push(r);
    else out.set(id, [r]);
  };
  for (const r of relations) {
    put(r.source, r);
    if (r.target !== r.source) put(r.target, r);
  }
  return out;
}

export interface RelationRow {
  page: GNode;
  note: string;
}

export interface RelationGroup {
  kind: string;
  /** Every edge in the group is computed (derived from vault data): the group starts collapsed. */
  computed: boolean;
  rows: RelationRow[];
}

/**
 * The connected pages of `id`, one group per relation kind: groups with a stated (stored) edge first, then the
 * computed ones; larger groups first, then by kind. A page appears once per kind (its first note wins).
 */
export function relationGroups(
  id: string,
  index: ReadonlyMap<string, readonly GRelation[]>,
  byId: ReadonlyMap<string, GNode>,
  degreeOf: (n: GNode) => number,
): RelationGroup[] {
  const groups = new Map<string, { computed: boolean; rows: Map<string, RelationRow> }>();
  for (const r of index.get(id) ?? []) {
    const other = r.source === id ? r.target : r.source;
    const page = byId.get(other);
    if (!page || other === id) continue;
    let g = groups.get(r.kind);
    if (!g) groups.set(r.kind, (g = { computed: true, rows: new Map() }));
    if (r.origin !== "computed") g.computed = false;
    const seen = g.rows.get(other);
    if (!seen) g.rows.set(other, { page, note: r.note });
    else if (!seen.note && r.note) seen.note = r.note;
  }
  return [...groups.entries()]
    .map(([kind, g]) => ({
      kind,
      computed: g.computed,
      rows: [...g.rows.values()].sort((a, b) => degreeOf(b.page) - degreeOf(a.page)),
    }))
    .sort((a, b) => Number(a.computed) - Number(b.computed) || b.rows.length - a.rows.length || a.kind.localeCompare(b.kind));
}
