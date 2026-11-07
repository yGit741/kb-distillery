import { withAlpha, type CanvasColors } from "../canvasTheme";
import type { Role, WebSource } from "./thinking";

/**
 * "Show my thinking" on the canvas (flag `show-thinking`), drawn around a page's own type mark so type stays the
 * shape: the rest of the graph is grey and dim, a found page is back in colour, an opened page has a soft glow in its
 * own colour, a cited page a stronger glow and an ink badge with its citation number. No path lines, no rings for
 * "one link away", and nothing moves. Sizes are screen px (divided by the zoom).
 */

/** Opacity of the pages that are not part of the answer (grey as well): dark goes lower, its colours are luminous. */
export const THINK_DIM = { light: 0.28, dark: 0.18 } as const;

/** A soft halo in the page's own colour, under its mark: a radial fade, so no hard edge. */
export function drawGlow(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, color: string, role: Role, scale: number, dark: boolean): void {
  if (role === "found") return;
  const cited = role === "cited";
  const R = r + (cited ? 26 : 16) / scale;
  const peak = cited ? (dark ? 0.6 : 0.7) : dark ? 0.35 : 0.42;
  const g = ctx.createRadialGradient(x, y, r * 0.6, x, y, R);
  g.addColorStop(0, withAlpha(color, peak));
  g.addColorStop(1, withAlpha(color, 0));
  ctx.save();
  ctx.fillStyle = g;
  ctx.fillRect(x - R, y - R, 2 * R, 2 * R);
  ctx.restore();
}

/** The citation number: an ink disc with a background-coloured number, at the mark's upper right. */
export function drawCiteBadge(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, n: number, scale: number, c: CanvasColors): void {
  const br = 8 / scale;
  const bx = x + r * 0.75 + br * 0.4;
  const by = y - r * 0.75 - br * 0.4;
  ctx.save();
  ctx.beginPath();
  ctx.arc(bx, by, br, 0, 2 * Math.PI);
  ctx.fillStyle = c.text;
  ctx.fill();
  ctx.lineWidth = 2 / scale;
  ctx.strokeStyle = c.background;
  ctx.stroke();
  ctx.fillStyle = c.background;
  ctx.font = `600 ${10 / scale}px ${c.font}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(n), bx, by + 0.5 / scale);
  ctx.restore();
}

/** The ring around a cited page whose words the reader points at in the answer. */
export function drawHotRing(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, scale: number, c: CanvasColors): void {
  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, r + 6 / scale, 0, 2 * Math.PI);
  ctx.lineWidth = 2 / scale;
  ctx.strokeStyle = c.text;
  ctx.stroke();
  ctx.restore();
}

/** A popped source scales in once (no other motion); still under reduced motion. */
export const POP_MS = 320;
export function popScale(at: number | undefined, now: number): number {
  if (at === undefined) return 1;
  const p = Math.min(1, Math.max(0, (now - at) / POP_MS));
  return 1 - Math.pow(1 - p, 3);
}

type Pt = { x: number; y: number };

/**
 * Where a web source sits: near the pages it is about, at the first of eight fixed directions with no page close by.
 * Deterministic, so the same answer always puts it in the same place. `gap` is in graph units.
 */
export function webSpot(about: readonly Pt[], others: readonly Pt[], gap: number, index: number): Pt | null {
  if (!about.length) return null;
  const cx = about.reduce((a, p) => a + p.x, 0) / about.length;
  const cy = about.reduce((a, p) => a + p.y, 0) / about.length;
  const free = (p: Pt) => others.every((o) => Math.hypot(o.x - p.x, o.y - p.y) > gap * 0.7);
  for (let ring = 1; ring <= 3; ring++) {
    for (let i = 0; i < 8; i++) {
      const a = -Math.PI / 4 + ((i + index * 3) % 8) * (Math.PI / 4);
      const p = { x: cx + Math.cos(a) * gap * ring, y: cy + Math.sin(a) * gap * ring };
      if (free(p)) return p;
    }
  }
  return { x: cx + gap * 3, y: cy };
}

/**
 * An opened web source: a temporary mark (a dashed ring with a globe), labelled "web source · host", tied by dashed
 * lines (an inference) to the pages its round was about. It is not a page and leaves with the thinking view.
 */
export function drawWebSource(ctx: CanvasRenderingContext2D, w: WebSource, at: Pt, about: readonly Pt[], scale: number, c: CanvasColors): void {
  const r = 10 / scale;
  ctx.save();
  ctx.setLineDash([5 / scale, 4 / scale]);
  ctx.lineWidth = 1.4 / scale;
  ctx.strokeStyle = withAlpha(c.muted, 0.9);
  for (const p of about) {
    ctx.beginPath();
    ctx.moveTo(at.x, at.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.arc(at.x, at.y, r, 0, 2 * Math.PI);
  ctx.fillStyle = c.background;
  ctx.fill();
  ctx.setLineDash([3 / scale, 2 / scale]);
  ctx.lineWidth = 1.6 / scale;
  ctx.strokeStyle = c.muted;
  ctx.stroke();
  ctx.setLineDash([]);
  // the globe: an outline, one meridian and the equator
  const g = r * 0.55;
  ctx.lineWidth = 1.2 / scale;
  ctx.beginPath();
  ctx.arc(at.x, at.y, g, 0, 2 * Math.PI);
  ctx.moveTo(at.x - g, at.y);
  ctx.lineTo(at.x + g, at.y);
  ctx.stroke();
  ctx.beginPath();
  ctx.ellipse(at.x, at.y, g * 0.45, g, 0, 0, 2 * Math.PI);
  ctx.stroke();
  const fs = 12 / scale;
  ctx.font = `${fs}px ${c.font}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.lineWidth = 3 / scale;
  ctx.strokeStyle = c.background;
  const label = `web source · ${w.host}`;
  ctx.strokeText(label, at.x, at.y + r + 4 / scale);
  ctx.fillStyle = c.text;
  ctx.fillText(label, at.x, at.y + r + 4 / scale);
  ctx.restore();
}
