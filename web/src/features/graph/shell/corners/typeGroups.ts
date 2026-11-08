import { glyphOf, GLYPH_LABEL, markOf, MARK_KEY, TYPE_LABEL_OVERRIDE } from "../../encoding/spec";
import type { TypeRow } from "../../legendModel";

/** One entry of the page-type bar: every type that shares an icon, counted together. Display only: types keep their own ids. */
export interface TypeGroup {
  /** the icon they share: a concept's or collection's mark, a source's glyph */
  key: string;
  /** the first member's id (it also draws the icon) */
  id: string;
  label: string;
  total: number;
  /** every member is drawn (one hidden member reads as dimmed, and pressing the entry shows them all) */
  shown: boolean;
  members: readonly TypeRow[];
}

export const typeName = (r: TypeRow): string => TYPE_LABEL_OVERRIDE[r.id] ?? r.label;

/** Names that read the same in the plural. */
const SAME = new Set(["Mail", "Slides", "Handwritten", "People"]);
const IRREGULAR: Readonly<Record<string, string>> = { Person: "People" };

/** The one place a singular legend name becomes a plural: "Article / post" -> "Articles / posts". */
export function pluralize(label: string): string {
  return label
    .split(" / ")
    .map((w) => (IRREGULAR[w] ?? (SAME.has(w) || w.endsWith("s") ? w : `${w}s`)))
    .join(" / ");
}

const MARK_LABEL: Readonly<Record<string, string>> = Object.fromEntries(MARK_KEY.map((k) => [k.mark, k.label]));

/** Group rows that share an icon, in the order each icon first appears. Sources group by glyph, everything else by mark. */
export function groupTypes(rows: readonly TypeRow[]): TypeGroup[] {
  const by = new Map<string, TypeRow[]>();
  for (const r of rows) {
    // a non-source type that still has the fallback mark (a kit type not yet registered) stands alone
    const key = r.layer === "source" ? `glyph:${glyphOf(r.id)}` : markOf(r.id) === "source" ? `id:${r.id}` : `mark:${markOf(r.id)}`;
    by.set(key, [...(by.get(key) ?? []), r]);
  }
  return [...by.entries()].map(([key, members]) => {
    const first = members[0]!;
    const shared = key.startsWith("glyph:") ? GLYPH_LABEL[glyphOf(first.id)] : (MARK_LABEL[markOf(first.id)] ?? typeName(first));
    return {
      key,
      id: first.id,
      // a source icon always reads as its plural name; a lone concept or collection type keeps its own label
      label: members.length === 1 && first.layer !== "source" ? typeName(first) : pluralize(shared),
      total: members.reduce((n, r) => n + r.total, 0),
      shown: members.every((r) => r.shown),
      members,
    };
  });
}
