import createForceGraph, { type ForceGraphInstance, type NodeObject } from "force-graph";
import { useEffect, useRef, useState } from "react";
import { drawNode, inkRadius, LABEL, outerRadius, personInitials, readCanvasColors, shortTitle, SOURCE_GLYPH_PX, withAlpha, wrapLabel, type ColorChannel, type NodeState } from "@/features/graph/encoding";
import type { Importance } from "@/features/graph/lab/importance";
import type { GNode } from "@/features/graph/types";
import { cn } from "@/lib/utils";
import { useTheme } from "@/theme/theme";
import { fitToBox, placeCardLabels, type LabelAsk } from "./cardLayout";
import type { Sample } from "./samplers";

/** Card canvas height in CSS px when not filling its parent; the width follows the card. */
export const GRAPH_HEIGHT = 220;
/** Node radius in screen px, by degree inside the sample: the same size at any zoom. */
export const R_MIN = 4;
export const R_MAX = 14;
/** Off-screen simulation ticks before the one and only draw: the card never shows the layout settling. */
const WARMUP = 160;
/** Label text: 12 px, wrapped to two lines of LABEL_WRAP px. */
const LABEL_PX = 12;
const LABEL_WRAP = 150;
/** Unforced labels at rest: one per LABEL_SPACING px of width, at most LABEL_MAX. */
const LABEL_SPACING = 120;
const LABEL_MAX = 9;

type Node = NodeObject & { id: string; g: GNode; r: number; gx?: number; gy?: number };

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


/**
 * The intro card's ego graph, static: the force layout settles off screen (`warmupTicks`), then is stretched to
 * fill the measured box (`fitToBox`, again on every resize) and pinned, so graph coords are screen px. Nodes and
 * 12 px labels are fixed sizes; labels (`placeCardLabels`): the focus, the ringed source and the hovered node
 * first, then the top hubs by importance, each fully inside the canvas and clear of nodes and other labels; hover
 * also shows the full title above. No wheel zoom, no pan, no drag: a click picks the node.
 */
export function SampleGraph({
  sample,
  byId,
  imp,
  ring = null,
  color,
  onPick,
  fill = false,
}: {
  sample: Sample;
  byId: ReadonlyMap<string, GNode>;
  imp: Importance;
  /** A second ringed node (the drawn source). */
  ring?: string | null;
  /** The card's colour channel (Home: theme, like Map); the legend under the card titles it. */
  color: ColorChannel;
  onPick: (id: string) => void;
  /** Take the parent's height instead of GRAPH_HEIGHT. */
  fill?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<string | null>(null);
  const hoverRef = useRef<string | null>(null);
  hoverRef.current = hover;
  const ringRef = useRef(ring);
  ringRef.current = ring;
  const theme = useTheme((t) => t.theme);
  const colorsRef = useRef(readCanvasColors());
  const colorRef = useRef(color);
  colorRef.current = color;
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const fg = useRef<ForceGraphInstance | null>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    // the chrome colours follow the theme without restarting the layout (colorsRef, refreshed below)
    const colors = colorsRef.current;
    const r = radii(sample);
    const nodes: Node[] = sample.nodes
      .map((id) => byId.get(id))
      .filter((g): g is GNode => !!g)
      .map((g) => ({ id: g.id, g, r: inkRadius(g.type, r.get(g.id) ?? R_MIN) }));
    const known = new Set(nodes.map((n) => n.id));
    const initials = personInitials(nodes.map((n) => n.g));
    const links = sample.links.filter(([a, b]) => known.has(a) && known.has(b)).map(([source, target]) => ({ source, target }));
    const hubs = nodes
      .map((n) => n.id)
      .sort((a, b) => (imp.score.get(b) ?? 0) - (imp.score.get(a) ?? 0) || a.localeCompare(b));
    let settled = false;
    const g = createForceGraph()(el);
    fg.current = g;
    const W = () => el.clientWidth || 300;
    const H = () => el.clientHeight || GRAPH_HEIGHT;
    const fit = () => {
      if (!settled || !el.clientWidth || !el.clientHeight) return;
      const pts = fitToBox(nodes.map((n) => ({ x: n.gx ?? 0, y: n.gy ?? 0 })), W(), H());
      nodes.forEach((n, i) => {
        n.x = n.fx = pts[i]!.x;
        n.y = n.fy = pts[i]!.y;
      });
      g.zoom(1, 0);
      g.centerAt(W() / 2, H() / 2, 0);
    };
    g.width(W())
      .height(H())
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
        if (!settled) return;
        const dpr = (ctx.canvas.width / (el.clientWidth || 1)) || 1;
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        const items = nodes.map((n) => {
          const p = g.graph2ScreenCoords(n.x ?? 0, n.y ?? 0);
          // labels keep clear of the whole mark (a collection's outer ring, a ring's stroke)
          return { id: n.id, n: n.g, x: p.x, y: p.y, r: outerRadius(n.g.type, n.r) };
        });
        const hov = hoverRef.current;
        const ringId = ringRef.current;
        // the shared encoding (@/features/graph/encoding): the same marks, glyphs and state rings as the Full Graph
        nodes.forEach((n, i) => {
          const it = items[i]!;
          const state: NodeState = it.id === sample.focus ? "focus" : it.id === ringId ? "drawn" : it.id === hov ? "hover" : null;
          drawNode(ctx, n.g.type, {
            x: it.x,
            y: it.y,
            r: n.r,
            color: colorRef.current.color(n.g),
            background: colors.background,
            font: colors.font,
            ring: colors.ring,
            initials: initials.get(n.id),
            state,
            glyph: n.r >= SOURCE_GLYPH_PX || it.id === hov,
          });
        });
        const forced = [sample.focus, ringId, hov].filter((id, i, a): id is string => !!id && known.has(id) && a.indexOf(id) === i);
        const budget = Math.min(LABEL_MAX, Math.floor(W() / LABEL_SPACING));
        const rest = hubs.filter((id) => !forced.includes(id)).slice(0, budget);
        const asks: LabelAsk[] = [...forced, ...rest].map((id) => {
          const n = byId.get(id)!;
          const weight = id === sample.focus ? 600 : 400;
          ctx.font = `${weight} ${LABEL_PX}px ${colors.font}`;
          const m = (t: string) => ctx.measureText(t).width;
          const lines = wrapLabel(shortTitle(n, "short"), LABEL_WRAP, 2, m, 40);
          return { id, lines, w: Math.max(...lines.map(m)), forced: forced.includes(id) };
        });
        const lineH = LABEL_PX * 1.2;
        const placed = placeCardLabels(items, asks, W(), H(), lineH);
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.lineJoin = "round";
        for (const p of placed) {
          ctx.font = `${p.id === sample.focus ? 600 : 400} ${LABEL_PX}px ${colors.font}`;
          const cx = (p.box[0] + p.box[2]) / 2;
          const top = (p.box[1] + p.box[3]) / 2 - ((p.lines.length - 1) * lineH) / 2;
          p.lines.forEach((line, i) => {
            ctx.lineWidth = LABEL.halo;
            ctx.strokeStyle = colors.background;
            ctx.strokeText(line, cx, top + i * lineH);
            ctx.fillStyle = p.id === ringId ? colors.ring : colors.text;
            ctx.fillText(line, cx, top + i * lineH);
          });
        }
        // for e2e checks: node centres (layer:id:x,y) and label boxes in canvas px
        el.dataset.nodes = items.map((it) => `${it.n.layer}:${it.id}:${Math.round(it.x)},${Math.round(it.y)}`).join(";");
        el.dataset.labels = placed.map((p) => `${p.id}:${p.box.map(Math.round).join(",")}`).join(";");
        ctx.restore();
      })
      .onNodeHover((n) => {
        setHover((n as Node | null)?.id ?? null);
        el.style.cursor = n ? "pointer" : "";
      })
      .onNodeClick((n) => pickRef.current((n as Node).id))
      .onEngineStop(() => {
        if (settled) return;
        for (const n of nodes) {
          n.gx = n.x ?? 0;
          n.gy = n.y ?? 0;
        }
        settled = true;
        fit();
      });
    const ro = new ResizeObserver(() => {
      g.width(W()).height(H());
      fit();
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      g._destructor();
      fg.current = null;
      el.replaceChildren();
    };
  }, [sample, byId, imp]);

  // labels and rings follow the hover and the ringed source without restarting the layout
  useEffect(() => {
    // force-graph 1.x has no public refresh: a zero-length zoom to the current scale flags its redraw
    const g = fg.current;
    g?.zoom(g.zoom(), 0);
  }, [hover, ring, color]);

  // a theme switch: re-read the chrome colours in place (the effect above draws through the same object), then redraw
  useEffect(() => {
    Object.assign(colorsRef.current, readCanvasColors());
    const g = fg.current;
    g?.zoom(g.zoom(), 0);
  }, [theme]);

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
        <p className="pointer-events-none absolute inset-x-2 top-2 line-clamp-2 rounded bg-popover/90 px-2 py-1 text-xs text-popover-foreground shadow-sm">
          {shortTitle(hovered, "title", true)}
        </p>
      )}
    </div>
  );
}
