import type { CanvasColors } from "../encoding/theme";

/**
 * The quiet source count on a concept (flag graph-intent, Concepts view): a small number at the node's upper right,
 * on the canvas colour so it reads over a link, in the muted ink so it never competes with the label.
 */
export function drawSourceCount(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, count: number, scale: number, c: CanvasColors, alpha = 1): void {
  const text = count > 99 ? "99+" : String(count);
  const size = 9.5 / scale;
  const bx = x + r * 0.78 + size * 0.35;
  const by = y - r * 0.78 - size * 0.2;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.font = `500 ${size}px ${c.font}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  ctx.lineWidth = 3 / scale;
  ctx.strokeStyle = c.background;
  ctx.strokeText(text, bx, by);
  ctx.fillStyle = c.muted;
  ctx.fillText(text, bx, by);
  ctx.restore();
}
