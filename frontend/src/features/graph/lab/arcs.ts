import { withAlpha, type CanvasColors } from "../canvasTheme";
import type { Arc } from "../tools/decor";
import type { SimNode } from "../types";

/**
 * Chords between theme anchors, under the graph: the level-2 spectrum as a picture. Each chord bows toward
 * the ring's centre so the strongest pairs read as a bundle through the middle; width and opacity grow
 * with the coefficient. Pairs that meet less than chance (`apart`) are thin dashed lines in the muted
 * colour (graph coordinates: called with force-graph's transform).
 */
export function drawArcs(ctx: CanvasRenderingContext2D, nodes: readonly SimNode[], arcs: readonly Arc[], scale: number, colors: CanvasColors): void {
  const at = new Map<string, SimNode>();
  for (const n of nodes) if (n.x != null && n.y != null) at.set(n.id, n);
  let cx = 0;
  let cy = 0;
  let k = 0;
  for (const a of arcs) for (const id of [a.a, a.b]) {
    const n = at.get(id);
    if (n) {
      cx += n.x as number;
      cy += n.y as number;
      k++;
    }
  }
  if (!k) return;
  cx /= k;
  cy /= k;
  ctx.save();
  ctx.lineCap = "round";
  // dashed "apart" chords first, so the solid ones sit on top
  for (const a of [...arcs].sort((p, q) => Number(!!q.apart) - Number(!!p.apart) || p.w - q.w)) {
    const s = at.get(a.a);
    const t = at.get(a.b);
    if (!s || !t) continue;
    const w = Math.max(0, Math.min(1, a.w));
    // control point: the midpoint pulled 45% of the way to the centre
    const mx = ((s.x as number) + (t.x as number)) / 2;
    const my = ((s.y as number) + (t.y as number)) / 2;
    const qx = mx + (cx - mx) * 0.45;
    const qy = my + (cy - my) * 0.45;
    ctx.beginPath();
    ctx.moveTo(s.x as number, s.y as number);
    ctx.quadraticCurveTo(qx, qy, t.x as number, t.y as number);
    if (a.apart) {
      // the grey link mesh is thin and solid: a dashed chord has to be darker and wider to read against it
      ctx.setLineDash([9 / scale, 6 / scale]);
      ctx.strokeStyle = withAlpha(colors.text, 0.3 + 0.3 * w);
      ctx.lineWidth = 2 / scale;
    } else {
      ctx.setLineDash([]);
      ctx.strokeStyle = withAlpha(colors.ring, 0.18 + 0.52 * w);
      ctx.lineWidth = (1.2 + 7 * w) / scale;
    }
    ctx.stroke();
  }
  ctx.restore();
}
