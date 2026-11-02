/** Covector picture: pure geometry, kept apart from the canvas so it can be tested. */

export const SCALE = 50; // pixels per math unit
export const SIZE = 600; // canvas width and height in pixels
export const SLICES = 40; // level sets are drawn for k = -SLICES … SLICES

export interface Inputs {
  vx: number;
  vy: number;
  ux: number;
  uy: number;
}

export interface Stats {
  /** ||v||, the length of the covector generator. */
  vLen: number;
  /** Distance between neighbouring level sets, 1/||v||; null when v is zero (the grid is infinitely coarse). */
  spacing: number | null;
  /** k = ω(u) = v · u, how many level sets the test vector crosses. */
  score: number;
}

export function stats({ vx, vy, ux, uy }: Inputs): Stats {
  const vLen = Math.sqrt(vx * vx + vy * vy);
  return { vLen, spacing: vLen > 0 ? 1 / vLen : null, score: vx * ux + vy * uy };
}

/** Text of the three readouts, formatted as the page always showed them. */
export function readouts(i: Inputs) {
  const s = stats(i);
  return {
    vLen: s.vLen.toFixed(2),
    spacing: s.spacing === null ? "∞" : s.spacing.toFixed(2),
    score: s.score.toFixed(2),
  };
}

export interface Slice {
  k: number;
  /** Canvas coordinates of the two far ends of the level line. */
  from: [number, number];
  to: [number, number];
}

/** The level sets ω = k, each a line perpendicular to v at distance k/||v||² along v. Empty when v is zero. */
export function slices({ vx, vy }: Inputs, size = SIZE, scale = SCALE): Slice[] {
  const vLen = Math.sqrt(vx * vx + vy * vy);
  if (!(vLen > 0)) return [];
  const origin = size / 2;
  const dirX = vx / vLen;
  const dirY = vy / vLen;
  const perpX = -dirY;
  const perpY = dirX;
  const out: Slice[] = [];
  for (let k = -SLICES; k <= SLICES; k++) {
    const cx = origin + ((k * dirX) / vLen) * scale;
    const cy = origin - ((k * dirY) / vLen) * scale;
    out.push({ k, from: [cx + perpX * 1000, cy - perpY * 1000], to: [cx - perpX * 1000, cy + perpY * 1000] });
  }
  return out;
}

/** Math point -> canvas point (y points up in the picture). */
export const toCanvas = (x: number, y: number, size = SIZE, scale = SCALE): [number, number] => [
  size / 2 + x * scale,
  size / 2 - y * scale,
];
