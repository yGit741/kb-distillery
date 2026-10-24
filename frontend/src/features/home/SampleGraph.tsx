import createForceGraph, { type ForceGraphInstance, type NodeObject } from "force-graph";
import { useEffect, useRef, useState } from "react";
import { readCanvasColors, withAlpha } from "@/features/graph/canvasTheme";
import type { GNode } from "@/features/graph/types";
import { cn } from "@/lib/utils";
import { typeColor } from "@/theme/palette";
import type { Sample } from "./samplers";

/** Card canvas height in CSS px; the width follows the card. */
export const GRAPH_HEIGHT = 220;

/** Labels wrap at this many screen px, on at most LABEL_LINES lines. */
const LABEL_WIDTH = 150;
const LABEL_LINES = 3;
/** Fit leaves room for labels under the outer nodes; small samples stop at MAX_ZOOM. */
const FIT_PADDING = 40;
const MAX_ZOOM = 2;

type Node = NodeObject & { id: string; title: string; type: string; r: number };

/** Most labels drawn at rest; the hovered node is always labelled on top of these. */
const MAX_LABELS = 5;

interface Box {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

export const overlaps = (a: Box, b: Box): boolean => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

/** Hovered node first, then the focus, then the rest by importance. */
export function labelOrder<T extends { id: string }>(nodes: readonly T[], focus: string, hover: string | null, score: ReadonlyMap<string, number>): T[] {
  const rank = (n: T) => (n.id === hover ? 2 : n.id === focus ? 1 : 0);
  return [...nodes].sort((a, b) => rank(b) - rank(a) || (score.get(b.id) ?? 0) - (score.get(a.id) ?? 0) || a.id.localeCompare(b.id));
}

/** Greedy word wrap; only the last allowed line gets an ellipsis, and only if words remain. */
export function wrap(text: string, width: number, measure: (s: string) => number, maxLines = LABEL_LINES): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let cur = "";
  for (let i = 0; i < words.length; i++) {
    const next = cur ? `${cur} ${words[i]}` : (words[i] as string);
    if (!cur || measure(next) <= width) {
      cur = next;
      continue;
    }
    lines.push(cur);
    cur = words[i] as string;
    if (lines.length === maxLines - 1) {
      const rest = words.slice(i).join(" ");
      if (measure(rest) <= width) return [...lines, rest];
      let cut = rest;
      while (cut.length > 1 && measure(`${cut}…`) > width) cut = cut.slice(0, -1);
      return [...lines, `${cut.trimEnd()}…`];
    }
  }
  if (cur) lines.push(cur);
  return lines;
}

/** Radius 3–7 px by degree inside the sample, so the focus and its hubs read first. */
export function radii(sample: Pick<Sample, "nodes" | "links">): Map<string, number> {
  const deg = new Map(sample.nodes.map((id) => [id, 0]));
  for (const [a, b] of sample.links) {
    deg.set(a, (deg.get(a) ?? 0) + 1);
    deg.set(b, (deg.get(b) ?? 0) + 1);
  }
  const max = Math.max(1, ...deg.values());
  return new Map([...deg].map(([id, d]) => [id, 3 + (4 * d) / max]));
}

/**
 * A small live force graph for one Home card. The simulation runs a short while, then freezes and fits;
 * the canvas is only created once the card scrolls into view. The wheel zooms only while the card has
 * focus, so scrolling the page never gets caught by a card.
 */
export function SampleGraph({
  sample,
  byId,
  score,
  onOpen,
  fill = false,
}: {
  sample: Sample;
  byId: ReadonlyMap<string, GNode>;
  score: ReadonlyMap<string, number>;
  onOpen: (id: string) => void;
  /** Take the parent's height instead of GRAPH_HEIGHT. */
  fill?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(typeof IntersectionObserver === "undefined");
  const [hover, setHover] = useState<string | null>(null);
  const hoverRef = useRef<string | null>(null);
  hoverRef.current = hover;
  const openRef = useRef(onOpen);
  openRef.current = onOpen;
  const fg = useRef<ForceGraphInstance | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el || visible) return;
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && setVisible(true), { rootMargin: "120px" });
    io.observe(el);
    return () => io.disconnect();
  }, [visible]);

  useEffect(() => {
    const el = host.current;
    if (!el || !visible) return;
    const colors = readCanvasColors();
    const r = radii(sample);
    const nodes: Node[] = sample.nodes.map((id) => ({ id, title: byId.get(id)?.title || id, type: byId.get(id)?.type ?? "", r: r.get(id) ?? 3 }));
    const links = sample.links.map(([source, target]) => ({ source, target }));
    const g = createForceGraph()(el);
    fg.current = g;
    g.width(el.clientWidth || 300)
      .height(el.clientHeight || GRAPH_HEIGHT)
      .backgroundColor("rgba(0,0,0,0)")
      .graphData({ nodes, links })
      .nodeId("id")
      .nodeLabel(() => "")
      .nodeRelSize(1)
      .nodeVal((n) => (n as Node).r ** 2)
      .linkColor(() => withAlpha(colors.link, 0.35))
      .linkWidth(0.8)
      .cooldownTicks(60)
      .enableZoomInteraction(false)
      .enablePanInteraction(true)
      .enableNodeDrag(true)
      .nodeCanvasObjectMode(() => "replace")
      .nodeCanvasObject((obj, ctx, scale) => {
        const n = obj as Node;
        const x = n.x ?? 0;
        const y = n.y ?? 0;
        ctx.beginPath();
        ctx.arc(x, y, n.r, 0, 2 * Math.PI);
        ctx.fillStyle = typeColor(n.type);
        ctx.fill();
        if (n.id === sample.focus) {
          ctx.lineWidth = 1.5 / scale;
          ctx.strokeStyle = colors.ring;
          ctx.stroke();
        }
      })
      // labels last, in priority order (hovered, focus, best-scored), skipping any that would overlap one
      // already drawn: a dense card shows fewer labels instead of a pile of text
      .onRenderFramePost((ctx, scale) => {
        const size = 11 / scale;
        ctx.font = `${size}px ${colors.font}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.lineWidth = 3 / scale;
        ctx.strokeStyle = colors.background;
        ctx.fillStyle = colors.text;
        const placed: Box[] = [];
        for (const n of labelOrder(nodes, sample.focus, hoverRef.current, score)) {
          const lines = wrap(n.title, LABEL_WIDTH / scale, (s) => ctx.measureText(s).width);
          const w = Math.max(...lines.map((l) => ctx.measureText(l).width));
          const top = (n.y ?? 0) + n.r + 2 / scale;
          const box: Box = { x0: (n.x ?? 0) - w / 2, x1: (n.x ?? 0) + w / 2, y0: top, y1: top + lines.length * size * 1.2 };
          const forced = n.id === hoverRef.current;
          if (!forced && (placed.length >= MAX_LABELS || placed.some((b) => overlaps(b, box)))) continue;
          placed.push(box);
          lines.forEach((line, i) => {
            ctx.strokeText(line, n.x ?? 0, top + i * size * 1.2);
            ctx.fillText(line, n.x ?? 0, top + i * size * 1.2);
          });
        }
      })
      .onNodeHover((n) => {
        setHover((n as Node | null)?.id ?? null);
        el.style.cursor = n ? "pointer" : "";
      })
      .onNodeClick((n) => openRef.current((n as Node).id))
      .onEngineStop(() => {
        // fit, but never blow a three-node sample up to giant discs
        g.zoomToFit(0, FIT_PADDING);
        if (g.zoom() > MAX_ZOOM) g.zoom(MAX_ZOOM);
      });
    const ro = new ResizeObserver(() => g.width(el.clientWidth || 300).height(el.clientHeight || GRAPH_HEIGHT));
    ro.observe(el);
    return () => {
      ro.disconnect();
      g._destructor();
      fg.current = null;
      el.replaceChildren();
    };
  }, [visible, sample, byId, score]);

  // labels follow the hover without restarting the simulation
  useEffect(() => {
    const g = fg.current as (ForceGraphInstance & { refresh?: () => void }) | null;
    g?.refresh?.();
  }, [hover]);

  return (
    <div
      ref={box}
      tabIndex={0}
      role="img"
      aria-label={`Graph of ${sample.nodes.length} pages around ${byId.get(sample.focus)?.title ?? sample.focus}`}
      className={cn("relative overflow-hidden rounded-md bg-muted/30 outline-none focus-visible:ring-2 focus-visible:ring-ring", fill && "h-full min-h-0")}
      style={fill ? undefined : { height: GRAPH_HEIGHT }}
      onFocus={() => fg.current?.enableZoomInteraction(true)}
      onBlur={() => fg.current?.enableZoomInteraction(false)}
      onKeyDown={(e) => {
        if (e.key === "Enter") openRef.current(sample.focus);
      }}
    >
      <div ref={host} className="absolute inset-0" />
      {hover && (
        <p className="pointer-events-none absolute inset-x-2 bottom-2 truncate rounded bg-popover/90 px-2 py-1 text-xs text-popover-foreground shadow-sm">
          {byId.get(hover)?.title ?? hover}
        </p>
      )}
    </div>
  );
}
