import type { RelationProposal } from "@/api/types";

/** The confidence range in whole percent, clamped to 0..100 with min <= max. */
export interface Range {
  min: number;
  max: number;
}

export const FULL: Range = { min: 0, max: 100 };

export const PRESETS: readonly { label: string; range: Range }[] = [
  { label: "90–100", range: { min: 90, max: 100 } },
  { label: "70–90", range: { min: 70, max: 90 } },
  { label: "50–70", range: { min: 50, max: 70 } },
  { label: "0–50", range: { min: 0, max: 50 } },
  { label: "All", range: FULL },
];

const pct = (v: string | undefined, fallback: number): number => {
  const n = Number(v);
  return v !== undefined && v !== "" && Number.isFinite(n) ? Math.min(100, Math.max(0, Math.round(n))) : fallback;
};

/** Read `?min=&max=` (percent strings) into a valid range; a swapped pair is put in order. */
export function readRange(min: string | undefined, max: string | undefined): Range {
  const a = pct(min, FULL.min);
  const b = pct(max, FULL.max);
  return { min: Math.min(a, b), max: Math.max(a, b) };
}

/** URL form of a range: the full range is the default and leaves the URL empty. */
export function rangeToSearch(r: Range): { min?: string; max?: string } {
  return { ...(r.min !== FULL.min ? { min: String(r.min) } : {}), ...(r.max !== FULL.max ? { max: String(r.max) } : {}) };
}

export const sameRange = (a: Range, b: Range) => a.min === b.min && a.max === b.max;

export interface Group {
  slug: string;
  title: string;
  rows: RelationProposal[];
}

/** Rows grouped by subject page, groups with the strongest proposal first; rows keep their (best-first) order. */
export function groupBySubject(rows: readonly RelationProposal[]): Group[] {
  const by = new Map<string, Group>();
  for (const r of rows) {
    const g = by.get(r.from) ?? { slug: r.from, title: r.from_title, rows: [] };
    g.rows.push(r);
    by.set(r.from, g);
  }
  return [...by.values()];
}

/** Whole-percent label of a 0..1 confidence ("0.9" -> "90%"). */
export const percent = (c: number): string => `${Math.round(c * 100)}%`;
