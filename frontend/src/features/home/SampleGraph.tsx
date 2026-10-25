import createForceGraph, { type ForceGraphInstance, type NodeObject } from "force-graph";
import { useEffect, useRef, useState } from "react";
import { readCanvasColors, withAlpha, type CanvasColors } from "@/features/graph/canvasTheme";
import { DEFAULT_LAB, type LabConfig } from "@/features/graph/lab/config";
import type { Importance } from "@/features/graph/lab/importance";
import { FORCED, planLabels, shortTitle, type ScreenItem } from "@/features/graph/lab/labelPlan";
import type { GNode } from "@/features/graph/types";
import { cn } from "@/lib/utils";
import { typeColor } from "@/theme/palette";
import type { Sample } from "./samplers";

/** Card canvas height in CSS px when not filling its parent; the width follows the card. */
export const GRAPH_HEIGHT = 220;
/** Fit padding in screen px, and the zoom range a fit may land on (tiny samples never blow up). */
export const FIT_PADDING = 40;
export const ZOOM_MIN = 0.7;
export const ZOOM_MAX = 2;
/** Node radius in screen px, by degree inside the sample: the same size at any zoom. */
export const R_MIN = 4;
export const R_MAX = 14;
/** Off-screen simulation ticks before the one and only draw: the card never shows the layout settling. */
const WARMUP = 160;
/** Unforced labels at rest (the picked concept and the drawn source are always labelled). */
const HUB_LABELS = 3;

/** The big graph's label rules, sized for a card: screen scope, a count budget, 12 px labels. */
export const CARD_LAB: LabConfig = {
  ...DEFAULT_LAB,
  scope: "screen",
  strategy: "count",
  count: HUB_LABELS,
  zoomGrowth: 0,
  sizeMode: "uniform",
  base: 12,
  minPx: 12,
  zoomScale: 0,
  questionLabels: "short",
  leaderLines: false,
  wrapT1: 130,
  wrapT2: 130,
  maxLines: 2,
};

type Node = NodeObject & { id: string; g: GNode; r: number };

/** Screen radius R_MIN–R_MAX by degree inside the sample, so the focus and its hubs read first. */
export function radii(sample: Pick<Sample, "nodes" | "links">): Map<string, number> {
  const deg = new Map(sample.nodes.map((id) => [id, 0]));
  for (const [a, b] of sample.links) {
    deg.set(a, (deg.get(a) ?? 0) + 1);
    deg.set(b, (deg.get(b) ?? 0) + 1);
  }
  const max = Math.max(1, ...deg.values());
  return new Map([...deg].map(([id, d]) => [id, R_MIN + ((R_MAX - R_MIN) * d) / max]));
}

export const clampZoom = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));

/** One node in screen px: the graph's palette, a question as a hollow ring with "?", the selection ring. */
function drawNode(ctx: CanvasRenderingContext2D, n: GNode, x: number, y: number, r: number, colors: CanvasColors, ring: "focus" | "source" | null, hover: boolean) {
  const col = typeColor(n.type);
  if (ring || hover) {
    ctx.beginPath();
    ctx.arc(x, y, r + 3, 0, 2 * Math.PI);
    ctx.strokeStyle = withAlpha(colors.ring, ring ? 0.95 : 0.55);
    ctx.lineWidth = ring === "focus" ? 2.5 : 2;
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.arc(x, y, r, 0, 2 * Math.PI);
  if (n.type === "question") {
    ctx.fillStyle = colors.background;
    ctx.fill();
    ctx.strokeStyle = col;
    ctx.lineWidth = Math.max(1.5, r * 0.22);
    ctx.stroke();
    ctx.fillStyle = col;
    ctx.font = `600 ${r * 1.4}px ${colors.font}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("?", x, y + r * 0.08);
    return;
  }
  ctx.fillStyle = col;
  ctx.fill();
}

/**
 * The intro card's ego graph, static: the force layout settles off screen (`warmupTicks`), is drawn once and
 * fitted after the box is measured (and again on every resize), zoom clamped to [ZOOM_MIN, ZOOM_MAX]. Nodes and
 * 12 px labels are fixed screen sizes; labels come from the big graph's planner (forced: the focus and the
 * ringed source; then up to HUB_LABELS hubs; collisions flip or drop; hover shows the full title). No wheel zoom,
 * no pan, no drag: a click picks the node, the card's "Full Graph" is where you explore.
 */
export function SampleGraph({
  sample,
  byId,
  imp,
  ring = null,
  onPick,
  fill = false,
}: {
  sample: Sample;
  byId: ReadonlyMap<string, GNode>;
  imp: Importance;
  /** A second ringed node (the drawn source). */
  ring?: string | null;
  onPick: (id: string) => void;
  /** Take the parent's height instead of GRAPH_HEIGHT. */
  fill?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<string | null>(null);
  const hoverRef = useRef<string | null>(null);
  hoverRef.current = hover;
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const fg = useRef<ForceGraphInstance | null>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const colors = readCanvasColors();
    const r = radii(sample);
    const nodes: Node[] = sample.nodes
      .map((id) => byId.get(id))
      .filter((g): g is GNode => !!g)
      .map((g) => ({ id: g.id, g, r: r.get(g.id) ?? R_MIN }));
    const known = new Set(nodes.map((n) => n.id));
    const links = sample.links.filter(([a, b]) => known.has(a) && known.has(b)).map(([source, target]) => ({ source, target }));
    let settled = false;
    const g = createForceGraph()(el);
    fg.current = g;
    const fit = () => {
      if (!settled || !el.clientWidth || !el.clientHeight) return;
      g.zoomToFit(0, FIT_PADDING + R_MAX);
      g.zoom(clampZoom(g.zoom()), 0);
    };
    g.width(el.clientWidth || 300)
      .height(el.clientHeight || GRAPH_HEIGHT)
      .backgroundColor("rgba(0,0,0,0)")
      .graphData({ nodes, links })
      .nodeId("id")
      .nodeLabel(() => "")
      .nodeRelSize(1)
      .linkColor(() => withAlpha(colors.link, 0.35))
      .linkWidth(0.8)
      .warmupTicks(WARMUP)
      .cooldownTicks(0)
      .enableZoomInteraction(false)
      .enablePanInteraction(false)
      .enableNodeDrag(false)
      .nodeCanvasObjectMode(() => "replace")
      .nodeCanvasObject(() => {})
      // hit area in graph units follows the fixed screen radius
      .nodePointerAreaPaint((obj, color, ctx, scale) => {
        const n = obj as Node;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(n.x ?? 0, n.y ?? 0, (n.r + 2) / scale, 0, 2 * Math.PI);
        ctx.fill();
      })
      // nodes and labels in screen px, after the links: same size at any fit
      .onRenderFramePost((ctx) => {
        const dpr = (ctx.canvas.width / (el.clientWidth || 1)) || 1;
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        const items: ScreenItem[] = nodes.map((n) => {
          const p = g.graph2ScreenCoords(n.x ?? 0, n.y ?? 0);
          return { n: n.g, sx: p.x, sy: p.y, r: n.r };
        });
        const hov = hoverRef.current;
        items.forEach((it) => drawNode(ctx, it.n, it.sx, it.sy, it.r, colors, it.n.id === sample.focus ? "focus" : it.n.id === ring ? "source" : null, it.n.id === hov));
        const forced = new Map<string, number>([[sample.focus, FORCED.selected]]);
        if (ring) forced.set(ring, FORCED.selected);
        if (hov) forced.set(hov, FORCED.hover);
        const plan = planLabels({
          items,
          width: el.clientWidth,
          height: el.clientHeight,
          zr: 1,
          cfg: CARD_LAB,
          imp,
          forced,
          hops: null,
          prev: new Map(),
          obstacles: [],
          suppress: false,
          measure: (t, px, w) => {
            ctx.font = `${w} ${px}px ${colors.font}`;
            return ctx.measureText(t).width;
          },
        });
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.lineJoin = "round";
        for (const p of plan.placed) {
          ctx.font = `${p.id === sample.focus ? 600 : 400} ${p.px}px ${colors.font}`;
          const cx = (p.box[0] + p.box[2]) / 2;
          const top = (p.box[1] + p.box[3]) / 2 - ((p.lines.length - 1) * p.lineH) / 2;
          p.lines.forEach((line, i) => {
            ctx.lineWidth = 3;
            ctx.strokeStyle = colors.background;
            ctx.strokeText(line, cx, top + i * p.lineH);
            ctx.fillStyle = p.id === ring ? colors.ring : colors.text;
            ctx.fillText(line, cx, top + i * p.lineH);
          });
        }
        ctx.restore();
      })
      .onNodeHover((n) => {
        setHover((n as Node | null)?.id ?? null);
        el.style.cursor = n ? "pointer" : "";
      })
      .onNodeClick((n) => pickRef.current((n as Node).id))
      .onEngineStop(() => {
        settled = true;
        fit();
      });
    const ro = new ResizeObserver(() => {
      g.width(el.clientWidth || 300).height(el.clientHeight || GRAPH_HEIGHT);
      fit();
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      g._destructor();
      fg.current = null;
      el.replaceChildren();
    };
  }, [sample, byId, imp, ring]);

  // labels follow the hover without restarting the layout
  useEffect(() => {
    const g = fg.current as (ForceGraphInstance & { refresh?: () => void }) | null;
    g?.refresh?.();
  }, [hover]);

  const hovered = hover ? byId.get(hover) : undefined;
  return (
    <div
      tabIndex={0}
      role="img"
      aria-label={`Graph of ${sample.nodes.length} pages around ${byId.get(sample.focus)?.title ?? sample.focus}`}
      className={cn("relative overflow-hidden rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring", fill && "h-full min-h-0")}
      style={fill ? undefined : { height: GRAPH_HEIGHT }}
      onKeyDown={(e) => {
        if (e.key === "Enter") pickRef.current(sample.focus);
      }}
    >
      <div ref={host} className="absolute inset-0" />
      {hovered && (
        <p className="pointer-events-none absolute inset-x-2 top-2 truncate rounded bg-popover/90 px-2 py-1 text-xs text-popover-foreground shadow-sm">
          {shortTitle(hovered, "title", true)}
        </p>
      )}
    </div>
  );
}
