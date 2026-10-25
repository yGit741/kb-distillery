/**
 * The intro card's ego graph, placed for a fixed box: `fitToBox` stretches the settled force layout to fill the
 * canvas (centred, bounded anisotropy) and `placeCardLabels` puts labels where they are fully inside the canvas
 * and overlap neither a node nor another label. Pure functions, so the rules are unit tested.
 */

export type Box = [number, number, number, number];

/** Side and top padding of the fitted layout in px: room for a label beside an edge node. */
export const FIT_PAD_X = 64;
export const FIT_PAD_Y = 30;
/** How much wider than tall the layout may be stretched (and vice versa) to fill the box. */
export const MAX_ANISO = 2.4;
/** The largest scale a tiny sample may take: three nodes never spread over the whole card. */
export const MAX_SCALE = 6;

/** Graph coords → box coords: the bounding box scaled into [pad, W−pad] × [pad, H−pad] and centred. */
export function fitToBox(pts: readonly { x: number; y: number }[], W: number, H: number, padX = FIT_PAD_X, padY = FIT_PAD_Y): { x: number; y: number }[] {
  if (!pts.length) return [];
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const bw = x1 - x0;
  const bh = y1 - y0;
  const aw = Math.max(1, W - 2 * padX);
  const ah = Math.max(1, H - 2 * padY);
  let kx = bw > 0 ? aw / bw : Infinity;
  let ky = bh > 0 ? ah / bh : Infinity;
  const k = Math.min(kx, ky, MAX_SCALE);
  kx = Math.min(kx, k * MAX_ANISO, MAX_SCALE * MAX_ANISO);
  ky = Math.min(ky, k * MAX_ANISO, MAX_SCALE * MAX_ANISO);
  if (!Number.isFinite(kx)) kx = k;
  if (!Number.isFinite(ky)) ky = k;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  return pts.map((p) => ({ x: W / 2 + (p.x - cx) * kx, y: H / 2 + (p.y - cy) * ky }));
}

export interface LabelNode {
  id: string;
  x: number;
  y: number;
  r: number;
}

export interface LabelAsk {
  id: string;
  lines: string[];
  /** width of the widest line in px */
  w: number;
  /** forced labels (focus, ringed source, hover) try farther rings before they give up */
  forced: boolean;
}

export interface PlacedLabel extends LabelAsk {
  box: Box;
  lineH: number;
}

/** Compass offsets: right, left, below, above, then the diagonals. */
const DIRS: readonly (readonly [number, number])[] = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
  [1, 1],
  [-1, 1],
  [1, -1],
  [-1, -1],
];

const boxHitsCircle = (b: Box, x: number, y: number, r: number) => {
  const nx = Math.max(b[0], Math.min(x, b[2]));
  const ny = Math.max(b[1], Math.min(y, b[3]));
  return (nx - x) ** 2 + (ny - y) ** 2 < r * r;
};
const boxesHit = (a: Box, b: Box) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];

/**
 * Labels in priority order (`asks`). Each tries the eight compass slots around its node (forced ones also two
 * farther rings); a box crossing the edge is shifted back inside. A slot is taken only when the box is inside
 * [margin, W−margin] × [margin, H−margin] and clear of every node (+2 px) and every placed label; otherwise the
 * label is dropped. Nothing is ever clipped or drawn over a node.
 */
export function placeCardLabels(nodes: readonly LabelNode[], asks: readonly LabelAsk[], W: number, H: number, lineH: number, pad = 2, margin = 2): PlacedLabel[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const placed: PlacedLabel[] = [];
  for (const a of asks) {
    const n = byId.get(a.id);
    if (!n) continue;
    const w = a.w + 2 * pad;
    const h = a.lines.length * lineH + 2 * pad;
    if (w > W - 2 * margin || h > H - 2 * margin) continue;
    const rings = a.forced ? [3, 12, 24] : [3];
    let got: Box | null = null;
    search: for (const gap of rings)
      for (const [dx, dy] of DIRS) {
        const d = n.r + gap;
        const cx = Math.min(W - margin - w / 2, Math.max(margin + w / 2, n.x + dx * (d + w / 2)));
        const cy = Math.min(H - margin - h / 2, Math.max(margin + h / 2, n.y + dy * (d + h / 2)));
        const b: Box = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2];
        if (nodes.some((m) => boxHitsCircle(b, m.x, m.y, m.r + 2))) continue;
        if (placed.some((p) => boxesHit(b, p.box))) continue;
        got = b;
        break search;
      }
    if (got) placed.push({ ...a, box: got, lineH });
  }
  return placed;
}
