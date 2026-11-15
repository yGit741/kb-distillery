import type { CanvasColors } from "../encoding/theme";

/**
 * The quiet source count on a concept (flag graph-intent, Concepts view): a small number at the node's upper right,
 * on the canvas colour so it reads over a link, in the muted ink so it never competes with the label. `r` is the
 * mark's outer reach (`outerRadius`): the number sits a clear gap outside it, 30 degrees above the horizontal, so it
 * touches neither the ring nor a label above or beside the mark, at any zoom.
 */
export function countAnchor(x: number, y: number, r: number, size: number): { x: number; y: number } {
  const d = r + size * 0.9;
  return { x: x + d * Math.cos(Math.PI / 6), y: y - d * Math.sin(Math.PI / 6) };
}

export function drawSourceCount(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, count: number, scale: number, c: CanvasColors, alpha = 1): void {
  const text = count > 99 ? "99+" : String(count);
  const size = 9.5 / scale;
  const { x: bx, y: by } = countAnchor(x, y, r, size);
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
