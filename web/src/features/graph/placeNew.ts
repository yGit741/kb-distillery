/**
 * Where a page added by hand ("Add its sources", "See sources") is first drawn: beside the drawn page it hangs
 * from, on the nearest free spot of a spiral around it. The pages already drawn never move (app-ui, graph rule 19),
 * so the layout cannot make room: the newcomers take the room that is there, each clear of every other page.
 */
export interface Spot {
  id: string;
  x?: number;
  y?: number;
}

/** the least distance between two page centres, in graph units: wide enough that two source dots stay apart at the
 * zoom a whole view is framed at (a dot shrinks more slowly than the distances do, ./style semanticRadius) */
export const NEW_GAP = 44;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));
/** spiral steps tried per page before the last candidate is taken as it is */
const MAX_STEPS = 4000;

/**
 * Give every page in `fresh` that has no place yet, and a placed neighbour, a place of its own. Mutates the nodes;
 * returns the ids it placed. A page with several placed neighbours starts from their middle.
 */
export function placeNew(nodes: Spot[], links: readonly { source: string | { id: string }; target: string | { id: string } }[], fresh: ReadonlySet<string>, gap = NEW_GAP): string[] {
  const todo = nodes.filter((n) => fresh.has(n.id) && (n.x == null || n.y == null));
  if (!todo.length) return [];
  const byId = new Map(nodes.map((n) => [n.id, n] as const));
  const near = new Map<string, Spot[]>();
  for (const l of links) {
    const idOf = (e: string | { id: string }) => (typeof e === "string" ? e : e.id);
    const [a, b] = [byId.get(idOf(l.source)), byId.get(idOf(l.target))];
    if (!a || !b) continue;
    if (b.x != null && b.y != null) near.set(a.id, [...(near.get(a.id) ?? []), b]);
    if (a.x != null && a.y != null) near.set(b.id, [...(near.get(b.id) ?? []), a]);
  }
  // taken spots, in a grid of gap-sized cells: a candidate checks its own cell and the eight around it
  const cells = new Map<string, { x: number; y: number }[]>();
  const key = (x: number, y: number) => `${Math.floor(x / gap)}|${Math.floor(y / gap)}`;
  const take = (x: number, y: number) => {
    const k = key(x, y);
    cells.set(k, [...(cells.get(k) ?? []), { x, y }]);
  };
  const free = (x: number, y: number) => {
    const [cx, cy] = [Math.floor(x / gap), Math.floor(y / gap)];
    for (let i = -1; i <= 1; i++)
      for (let j = -1; j <= 1; j++) for (const p of cells.get(`${cx + i}|${cy + j}`) ?? []) if (Math.hypot(p.x - x, p.y - y) < gap) return false;
    return true;
  };
  for (const n of nodes) if (n.x != null && n.y != null) take(n.x, n.y);
  const placed: string[] = [];
  for (const n of todo) {
    const from = near.get(n.id);
    if (!from?.length) continue;
    const ax = from.reduce((s, p) => s + p.x!, 0) / from.length;
    const ay = from.reduce((s, p) => s + p.y!, 0) / from.length;
    let [x, y] = [ax, ay];
    // a sunflower spiral: each step a little further out, so the first free spot is the nearest one
    for (let i = 1; i <= MAX_STEPS; i++) {
      const r = gap * Math.sqrt(i);
      x = ax + r * Math.cos(i * GOLDEN);
      y = ay + r * Math.sin(i * GOLDEN);
      if (free(x, y)) break;
    }
    n.x = x;
    n.y = y;
    take(x, y);
    placed.push(n.id);
  }
  return placed;
}
