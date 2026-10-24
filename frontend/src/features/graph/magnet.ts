/** The magnetic pointer: the hovered page is the nearest one, not only the one under the pointer. */

export interface ScreenNode {
  id: string;
  x: number;
  y: number;
  /** Radius in screen pixels. */
  r: number;
}

export const REACH_MIN = 12;
export const REACH_MAX = 90;
export const REACH_SHARE = 0.6;
/** A current target is kept until another is this much closer, so a dense area does not flicker. */
export const STICKY = 1.2;

const rim = (n: ScreenNode, px: number, py: number) => Math.hypot(n.x - px, n.y - py) - n.r;

/** Rim-to-rim gap from `n` to its closest neighbour, screen px. */
export function gapOf(n: ScreenNode, all: readonly ScreenNode[]): number {
  let best = Infinity;
  for (const o of all) {
    if (o === n) continue;
    const d = Math.hypot(o.x - n.x, o.y - n.y) - n.r - o.r;
    if (d < best) best = d;
  }
  return Number.isFinite(best) ? Math.max(0, best) : 40;
}

/** How far a node's pull reaches: follows the spacing around it (density and zoom both count). */
export const reachOf = (n: ScreenNode, all: readonly ScreenNode[]): number =>
  Math.min(REACH_MAX, Math.max(REACH_MIN, gapOf(n, all) * REACH_SHARE));

/** Nearest node to the pointer within its own reach, or null (a miss). `current` is sticky. */
export function pickMagnetic(
  nodes: readonly ScreenNode[],
  px: number,
  py: number,
  current: string | null = null,
): string | null {
  let best: ScreenNode | null = null;
  let bd = Infinity;
  for (const n of nodes) {
    const d = rim(n, px, py);
    if (d < bd) {
      bd = d;
      best = n;
    }
  }
  if (!best) return null;
  const cur = current ? nodes.find((n) => n.id === current) : undefined;
  if (cur && cur !== best) {
    const td = rim(cur, px, py);
    if (td <= reachOf(cur, nodes) && td < bd * STICKY + 3) return cur.id;
  }
  return bd <= reachOf(best, nodes) ? best.id : null;
}

/** The eased bubble that joins the pointer to its magnetic target: radius (px) and strength (0..1). */
export interface Bubble {
  r: number;
  a: number;
}

/** One animation step toward the wanted radius and strength; `still` = prefers-reduced-motion. */
export function stepBubble(b: Bubble, want: number, strength: number, still: boolean): Bubble {
  return still ? { r: want, a: strength } : { r: b.r + (want - b.r) * 0.3, a: b.a + (strength - b.a) * 0.2 };
}

/** What the bubble aims for: it reaches past the target's rim and weakens toward the edge of its reach. */
export function bubbleAim(t: ScreenNode, px: number, py: number, all: readonly ScreenNode[]): { want: number; strength: number } {
  const want = Math.hypot(t.x - px, t.y - py) + t.r + 10;
  const strength = 1 - 0.55 * Math.min(1, Math.max(0, rim(t, px, py)) / reachOf(t, all));
  return { want, strength };
}

/** A soft radial bubble around the pointer plus a glow on the target, so the two read as one shape. */
export function drawBubble(
  ctx: CanvasRenderingContext2D,
  px: number,
  py: number,
  target: ScreenNode | null,
  b: Bubble,
  rgb: string,
): void {
  if (b.a <= 0.02 || b.r <= 2) return;
  const R = b.r * 1.12;
  const g = ctx.createRadialGradient(px, py, 0, px, py, R);
  g.addColorStop(0, `rgba(${rgb},${0.17 * b.a})`);
  g.addColorStop(0.6, `rgba(${rgb},${0.11 * b.a})`);
  g.addColorStop(1, `rgba(${rgb},0)`);
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(px, py, R, 0, Math.PI * 2);
  ctx.fill();
  if (!target) return;
  const g2 = ctx.createRadialGradient(target.x, target.y, target.r * 0.6, target.x, target.y, target.r + 16);
  g2.addColorStop(0, `rgba(${rgb},${0.3 * b.a})`);
  g2.addColorStop(1, `rgba(${rgb},0)`);
  ctx.fillStyle = g2;
  ctx.beginPath();
  ctx.arc(target.x, target.y, target.r + 16, 0, Math.PI * 2);
  ctx.fill();
}

/** "r,g,b" of a CSS colour (#rrggbb or rgb()/rgba()); the blue accent when it cannot be read. */
export function rgbOf(color: string): string {
  const c = color.trim();
  if (/^#[0-9a-f]{6}$/i.test(c)) return [1, 3, 5].map((o) => parseInt(c.slice(o, o + 2), 16)).join(",");
  const m = c.match(/\d+(\.\d+)?/g);
  return m && m.length >= 3 ? m.slice(0, 3).join(",") : "37,99,235";
}

/** The quiet arrow cursor as a CSS `cursor` value. A blob URL, not a data URL: the shared site carries no
 *  embedded images. Falls back to the system arrow where blob URLs are unavailable. */
export function magnetCursor(): string {
  const svg =
    "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'><path d='M7 4 L7 24.5 L12.4 19.4 L16 27.2 L19.4 25.7 L15.9 18 L23.2 18 Z' fill='#15171c' stroke='#fff' stroke-width='1.8' stroke-linejoin='round'/></svg>";
  try {
    return `url("${URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }))}") 7 4, default`;
  } catch {
    return "default";
  }
}
