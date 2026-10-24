import type { GNode } from "../types";

export interface Region {
  area: string;
  name: string;
  x: number;
  y: number;
  members: number;
}

type Pt = readonly [number, number];
type Positioned = GNode & { x?: number; y?: number };

const median = (xs: number[]): number => {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? (s[m] as number) : ((s[m - 1] as number) + (s[m] as number)) / 2;
};

/** Area slug -> its topic page's title ("implicit-regularization" -> "Implicit regularization"). */
export function areaNames(nodes: readonly GNode[]): Map<string, string> {
  const out = new Map<string, string>();
  for (const n of nodes) if (n.type === "topic" && n.areas[0]) out.set(n.areas[0], n.title || n.id);
  return out;
}

/** One region per primary area with at least `min` drawn pages, at the median of their positions, largest first. */
export function regionsOf(nodes: readonly Positioned[], names: ReadonlyMap<string, string>, min = 3): Region[] {
  const groups = new Map<string, Positioned[]>();
  for (const n of nodes) {
    const a = n.areas[0];
    if (!a || n.x == null || n.y == null || !Number.isFinite(n.x)) continue;
    const g = groups.get(a);
    if (g) g.push(n);
    else groups.set(a, [n]);
  }
  const out: Region[] = [];
  for (const [area, list] of groups) {
    if (list.length < min) continue;
    out.push({
      area,
      name: names.get(area) ?? area.replace(/-/g, " "),
      x: median(list.map((n) => n.x as number)),
      y: median(list.map((n) => n.y as number)),
      members: list.length,
    });
  }
  return out.sort((a, b) => b.members - a.members || a.area.localeCompare(b.area));
}

const cross = (o: Pt, a: Pt, b: Pt) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);

/** Convex hull (Andrew's monotone chain), counter-clockwise; fewer than 3 distinct points give them back. */
export function convexHull(points: readonly Pt[]): Pt[] {
  const p = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (p.length < 3) return p;
  const lower: Pt[] = [];
  for (const q of p) {
    while (lower.length >= 2 && cross(lower[lower.length - 2] as Pt, lower[lower.length - 1] as Pt, q) <= 0) lower.pop();
    lower.push(q);
  }
  const upper: Pt[] = [];
  for (let i = p.length - 1; i >= 0; i--) {
    const q = p[i] as Pt;
    while (upper.length >= 2 && cross(upper[upper.length - 2] as Pt, upper[upper.length - 1] as Pt, q) <= 0) upper.pop();
    upper.push(q);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

/** The hull of an area's core: the 70% of its pages closest to the median, so a few strays do not blow it up. */
export function coreHull(members: readonly Positioned[], keep = 0.7): Pt[] {
  const pts = members.filter((n) => n.x != null && n.y != null).map((n) => [n.x as number, n.y as number] as const);
  if (pts.length < 3) return [];
  const cx = median(pts.map((p) => p[0]));
  const cy = median(pts.map((p) => p[1]));
  const d = pts.map((p) => Math.hypot(p[0] - cx, p[1] - cy)).sort((a, b) => a - b);
  const cut = d[Math.floor(d.length * keep)] ?? 0;
  return convexHull(pts.filter((p) => Math.hypot(p[0] - cx, p[1] - cy) <= cut + 1e-9));
}
