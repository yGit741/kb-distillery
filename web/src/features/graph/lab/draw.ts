import { areaHue, semanticRadius } from "../style";
import { withAlpha, type CanvasColors } from "../canvasTheme";
import type { SimNode } from "../types";
import type { LabConfig } from "./config";
import type { Importance } from "./importance";
import { labelText, planLabels, type Box, type Placed, type Plan } from "./labelPlan";
import { coreHull, regionKey, regionsOf } from "./regions";

/** Per-label fade state: opacity, where it is heading, its offset and its last placement (kept while fading out). */
export interface FadeState {
  a: number;
  target: 0 | 1;
  pos: number;
  last: Placed;
  /** label centre minus node centre, CSS px */
  dx: number;
  dy: number;
}

export interface LabelLayerInput {
  ctx: CanvasRenderingContext2D;
  nodes: readonly SimNode[];
  /** the pages "fit to view" frames (the largest connected component); zoom 1× = they fit */
  fitIds: ReadonlySet<string>;
  /** CSS px size of the canvas */
  width: number;
  height: number;

  cfg: LabConfig;
  imp: Importance;
  forced: ReadonlyMap<string, number>;
  hops: ReadonlyMap<string, number> | null;
  /** nodes drawn faint (outside the highlight): their labels fade too */
  dim: (id: string) => boolean;
  radius: (n: SimNode) => number;
  colors: CanvasColors;
  areaNames: ReadonlyMap<string, string>;
  fades: Map<string, FadeState>;
  /** pointer in CSS px of the canvas, for the lens */
  pointer: { x: number; y: number } | null;
  hovered: string | null;
  dt: number;
  /** a node's colour on the canvas: a leader line takes it, so it reads as part of its node */
  nodeColor?: (n: SimNode) => string;
}

export interface LabelLayerResult {
  animating: boolean;
  plan: Plan;
  changes: number;
  zr: number;
}

/**
 * The zoom at which these pages fit the canvas, with ForceGraph.fit's padding: what "fit to view" shows. Labels grow
 * with zoom relative to this, and "zoomed out" means below it. Computed from the layout itself, so it is right
 * whatever fit or animation ran last.
 */
export function fitZoom(nodes: readonly { x?: number; y?: number }[], width: number, height: number): number {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const n of nodes) if (n.x != null && n.y != null && Number.isFinite(n.x) && Number.isFinite(n.y)) {
    xs.push(n.x);
    ys.push(n.y);
  }
  if (xs.length < 2) return 1;
  xs.sort((a, b) => a - b);
  ys.sort((a, b) => a - b);
  const q = (a: number[], p: number) => a[Math.min(a.length - 1, Math.max(0, Math.round(p * (a.length - 1))))] as number;
  const w = q(xs, 1) - q(xs, 0) || 1;
  const h = q(ys, 1) - q(ys, 0) || 1;
  // the same padding as ForceGraph.fit, so zoom 1× is what "fit to view" shows
  const pad = Math.round(Math.min(90, Math.max(24, width * 0.08)));
  return Math.min(Math.max(1, width - 2 * pad) / w, Math.max(1, height - 2 * pad) / h);
}

/** Height of the band at the canvas bottom that the page-type strip covers (24px + 3.5px edge gap + 8px air). */
const TYPES_STRIP_H = 36;

const toScreen = (m: DOMMatrix, pr: number, x: number, y: number) => [(m.a * x + m.c * y + m.e) / pr, (m.b * x + m.d * y + m.f) / pr] as const;

/** Faint hulls of each theme's core, under the nodes (graph coordinates: called with force-graph's transform). */
/** Trace `hull` grown by a disk of radius R as the current path (not drawn); false when it is too small. */
export function traceRoundedHull(ctx: CanvasRenderingContext2D, hull: readonly (readonly [number, number])[], R: number): boolean {
  if (hull.length < 3) return false;
  // the hull grown by a disk of radius R (Minkowski sum): edges pushed out along their normals, every corner an arc
  const n = hull.length;
  let area2 = 0;
  for (let i = 0; i < n; i++) {
    const [x0, y0] = hull[i]!;
    const [x1, y1] = hull[(i + 1) % n]!;
    area2 += x0 * y1 - x1 * y0;
  }
  const s = area2 >= 0 ? 1 : -1;
  // outward normal angle of edge i (hull[i] → hull[i+1])
  const normal = (i: number) => {
    const [x0, y0] = hull[i]!;
    const [x1, y1] = hull[(i + 1) % n]!;
    return Math.atan2(-(x1 - x0) * s, (y1 - y0) * s);
  };
  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const [x, y] = hull[i]!;
    ctx.arc(x, y, R, normal((i - 1 + n) % n), normal(i), s < 0);
  }
  ctx.closePath();
  return true;
}

export function drawHulls(
  ctx: CanvasRenderingContext2D,
  nodes: readonly SimNode[],
  scale: number,
  names: ReadonlyMap<string, string>,
  sigma = 2,
): void {
  const groups = new Map<string, SimNode[]>();
  for (const n of nodes) {
    const a = regionKey(n, names);
    if (!a || !names.has(a)) continue;
    const g = groups.get(a);
    if (g) g.push(n);
    else groups.set(a, [n]);
  }
  for (const [area, list] of groups) {
    const hull = coreHull(list, 0.7, sigma);
    if (!traceRoundedHull(ctx, hull, 30)) continue;
    const col = areaHue(area);
    ctx.fillStyle = withAlpha(col, 0.08);
    ctx.fill();
    ctx.strokeStyle = withAlpha(col, 0.12);
    ctx.lineWidth = 1 / scale;
    ctx.stroke();
  }
}

/**
 * The label layer, drawn in CSS pixels on top of the frame: region names when zoomed out, page labels from
 * the planner with fades, and the hover lens. Called from force-graph's post-frame hook with its transform.
 */
export function drawLabelLayer(i: LabelLayerInput): LabelLayerResult {
  const { ctx, cfg, colors } = i;
  const pr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const m = ctx.getTransform();
  const k = m.a / pr;
  const framed = i.fitIds.size > 1 ? i.nodes.filter((n) => i.fitIds.has(n.id)) : i.nodes;
  const zr = k / fitZoom(framed, i.width, i.height);
  ctx.save();
  ctx.setTransform(pr, 0, 0, pr, 0, 0);
  const font = colors.font;

  const regionsOn = cfg.regions === "with" || (cfg.regions === "auto" && zr < cfg.regionZoom);
  const suppress = regionsOn && cfg.regions === "auto" && cfg.regionsSuppress;
  const obstacles: Box[] = [];
  // the page-type strip sits at the bottom centre (24px tall, 3.5px from the edge, up to 560px wide when it is
  // folded), so no label is ever planned under it
  const stripW = Math.min(560, Math.max(0, i.width - 160));
  if (stripW > 0) obstacles.push([(i.width - stripW) / 2, i.height - TYPES_STRIP_H, (i.width + stripW) / 2, i.height]);
  const regionDraw: { text: string; x: number; y: number; px: number }[] = [];
  if (regionsOn) {
    const px = 22;
    ctx.font = `700 ${px}px ${font}`;
    for (const r of regionsOf(i.nodes, i.areaNames)) {
      const [sx, sy] = toScreen(m, pr, r.x, r.y);
      const text = r.name.toUpperCase();
      const w = ctx.measureText(text).width + text.length * 2;
      const b: Box = [sx - w / 2, sy - px / 2, sx + w / 2, sy + px / 2];
      if (obstacles.some((o) => o[0] < b[2] && o[2] > b[0] && o[1] < b[3] && o[3] > b[1])) continue;
      obstacles.push(b);
      regionDraw.push({ text, x: sx, y: sy, px });
    }
  }

  const items = [];
  for (const n of i.nodes) {
    if (n.x == null || n.y == null || !Number.isFinite(n.x) || !i.imp.score.has(n.id)) continue;
    const [sx, sy] = toScreen(m, pr, n.x, n.y);
    items.push({ n, sx, sy, r: semanticRadius(i.radius(n), k, zr) * k });
  }
  const prev = new Map<string, { shown: boolean; pos: number }>();
  for (const [id, f] of i.fades) prev.set(id, { shown: f.target === 1, pos: f.pos });
  const plan = planLabels({
    items,
    width: i.width,
    height: i.height,
    zr,
    cfg,
    imp: i.imp,
    forced: i.forced,
    hops: i.hops,
    prev,
    obstacles,
    suppress,
    measure: (text, px, weight) => {
      ctx.font = `${weight} ${px}px ${font}`;
      return ctx.measureText(text).width;
    },
  });

  // regions under the page labels
  if (regionDraw.length) {
    const fadeR = cfg.regions === "auto" ? Math.max(0.25, Math.min(1, (cfg.regionZoom - zr) / (cfg.regionZoom * 0.3))) : 1;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = colors.text;
    ctx.globalAlpha = 0.38 * fadeR;
    for (const r of regionDraw) {
      ctx.font = `700 ${r.px}px ${font}`;
      ctx.fillText(r.text.split("").join(" "), r.x, r.y);
    }
    ctx.globalAlpha = 1;
  }

  // fade targets
  const centre = (b: Box) => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] as const;
  const screenOf = new Map(items.map((it) => [it.n.id, it] as const));
  const shown = new Set<string>();
  let changes = 0;
  for (const p of plan.placed) {
    shown.add(p.id);
    const it = screenOf.get(p.id);
    const [cx, cy] = centre(p.box);
    const f = i.fades.get(p.id);
    const dx = it ? cx - it.sx : 0;
    const dy = it ? cy - it.sy : 0;
    if (!f || f.target !== 1) changes++;
    i.fades.set(p.id, { a: f?.a ?? 0, target: 1, pos: p.pos, last: p, dx, dy });
  }
  for (const [id, f] of i.fades) if (!shown.has(id) && f.target === 1) {
    f.target = 0;
    changes++;
  }

  // draw
  const step = cfg.fade > 0 ? i.dt / cfg.fade : 1;
  let animating = false;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const [id, f] of i.fades) {
    f.a = Math.max(0, Math.min(1, f.a + (f.target ? step : -step)));
    if (f.a > 0 && f.a < 1) animating = true;
    if (f.a <= 0 && !f.target) {
      i.fades.delete(id);
      continue;
    }
    const it = screenOf.get(id);
    if (!it) continue;
    const p = f.last;
    const cx = it.sx + f.dx;
    const cy = it.sy + f.dy;
    const hw = (p.box[2] - p.box[0]) / 2;
    const hh = (p.box[3] - p.box[1]) / 2;
    const alpha = f.a * (i.dim(id) ? 0.35 : 1);
    ctx.globalAlpha = alpha;
    ctx.font = `${p.weight} ${p.px}px ${font}`;
    // a squeezed-out forced label: a thin line from the node to the nearest point of its box
    if (p.leader && cfg.leaderLines) {
      ctx.strokeStyle = withAlpha(i.nodeColor ? i.nodeColor(p.n as SimNode) : colors.muted, 0.75);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(it.sx, it.sy);
      ctx.lineTo(Math.max(cx - hw, Math.min(cx + hw, it.sx)), Math.max(cy - hh, Math.min(cy + hh, it.sy)));
      ctx.stroke();
    }
    if (cfg.forcedPill && p.focus) {
      ctx.beginPath();
      ctx.roundRect(cx - hw, cy - hh, hw * 2, hh * 2, 4);
      ctx.fillStyle = withAlpha(colors.background, 0.9);
      ctx.fill();
      ctx.strokeStyle = withAlpha(colors.ring, 0.5);
      ctx.lineWidth = 1;
      ctx.stroke();
    } else if (cfg.bg === "box") {
      ctx.fillStyle = withAlpha(colors.background, 0.82);
      ctx.fillRect(cx - hw, cy - hh, hw * 2, hh * 2);
    }
    const { lines, lineH } = p;
    const halo = cfg.bg === "halo" && !(cfg.forcedPill && p.focus);
    ctx.fillStyle = cfg.weightTier && p.tier === 3 && !p.forced ? colors.muted : colors.text;
    lines.forEach((line, j) => {
      const ly = cy + (j - (lines.length - 1) / 2) * lineH + 0.5;
      if (halo) {
        ctx.lineJoin = "round";
        ctx.lineWidth = 3.5;
        ctx.strokeStyle = withAlpha(colors.background, 0.9);
        ctx.strokeText(line, cx, ly);
      }
      ctx.fillText(line, cx, ly);
    });
  }
  ctx.globalAlpha = 1;

  if (cfg.lens && i.pointer) drawLens(ctx, i, items, font);
  ctx.restore();
  return { animating, plan, changes, zr };
}

/** Excentric labels (Fekete & Plaisant): every page under the pointer, top N by score, in a column with leader lines. */
function drawLens(
  ctx: CanvasRenderingContext2D,
  i: LabelLayerInput,
  items: readonly { n: SimNode; sx: number; sy: number }[],
  font: string,
): void {
  const { x: px, y: py } = i.pointer as { x: number; y: number };
  const R = i.cfg.lensR;
  const hits = items.filter((it) => Math.hypot(it.sx - px, it.sy - py) <= R);
  ctx.beginPath();
  ctx.arc(px, py, R, 0, 2 * Math.PI);
  ctx.strokeStyle = withAlpha(i.colors.ring, 0.6);
  ctx.lineWidth = 1;
  ctx.stroke();
  if (!hits.length) return;
  const ranked = [...hits].sort((a, b) => (i.imp.score.get(b.n.id) ?? 0) - (i.imp.score.get(a.n.id) ?? 0));
  const shown = ranked.slice(0, i.cfg.lensMax).sort((a, b) => a.sy - b.sy);
  const lh = 16;
  const right = px + R + 220 < i.width;
  const colX = right ? px + R + 16 : px - R - 16;
  const top = Math.max(8, Math.min(i.height - shown.length * lh - 24, py - (shown.length * lh) / 2));
  ctx.font = `400 12px ${font}`;
  ctx.textBaseline = "middle";
  ctx.textAlign = right ? "left" : "right";
  shown.forEach((h, k) => {
    const ly = top + k * lh + lh / 2;
    ctx.strokeStyle = withAlpha(i.colors.muted, 0.6);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(h.sx, h.sy);
    ctx.lineTo(colX + (right ? -4 : 4), ly);
    ctx.stroke();
    const t = labelText(h.n, i.cfg.textField, i.cfg.maxChars);
    ctx.lineWidth = 3.5;
    ctx.lineJoin = "round";
    ctx.strokeStyle = withAlpha(i.colors.background, 0.9);
    ctx.strokeText(t, colX, ly);
    ctx.fillStyle = h.n.id === i.hovered ? i.colors.ring : i.colors.text;
    ctx.fillText(t, colX, ly);
  });
  if (hits.length > shown.length) {
    ctx.fillStyle = i.colors.muted;
    ctx.fillText(`+${hits.length - shown.length} more`, colX, top + shown.length * lh + lh / 2);
  }
}
