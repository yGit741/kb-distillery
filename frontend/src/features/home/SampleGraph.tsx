import createForceGraph, { type ForceGraphInstance, type NodeObject } from "force-graph";
import { useEffect, useRef, useState } from "react";
import { readCanvasColors, withAlpha } from "@/features/graph/canvasTheme";
import type { GNode } from "@/features/graph/types";
import { typeColor } from "@/theme/palette";
import type { Sample } from "./samplers";

/** Card canvas height in CSS px; the width follows the card. */
export const GRAPH_HEIGHT = 220;
/** Labels drawn without hovering: the focus plus this many best-scored nodes. */
const LABELS = 3;

type Node = NodeObject & { id: string; title: string; type: string; r: number };

const trunc = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

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
}: {
  sample: Sample;
  byId: ReadonlyMap<string, GNode>;
  score: ReadonlyMap<string, number>;
  onOpen: (id: string) => void;
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
    const labelled = new Set(
      [...sample.nodes].sort((a, b) => (score.get(b) ?? 0) - (score.get(a) ?? 0)).slice(0, LABELS).concat(sample.focus),
    );
    const nodes: Node[] = sample.nodes.map((id) => ({ id, title: byId.get(id)?.title || id, type: byId.get(id)?.type ?? "", r: r.get(id) ?? 3 }));
    const links = sample.links.map(([source, target]) => ({ source, target }));
    const g = createForceGraph()(el);
    fg.current = g;
    g.width(el.clientWidth || 300)
      .height(GRAPH_HEIGHT)
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
        if (!labelled.has(n.id) && hoverRef.current !== n.id) return;
        const size = 11 / scale;
        ctx.font = `${size}px ${colors.font}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.lineWidth = 3 / scale;
        ctx.strokeStyle = colors.background;
        const text = trunc(n.title, hoverRef.current === n.id ? 48 : 22);
        ctx.strokeText(text, x, y + n.r + 2 / scale);
        ctx.fillStyle = colors.text;
        ctx.fillText(text, x, y + n.r + 2 / scale);
      })
      .onNodeHover((n) => {
        setHover((n as Node | null)?.id ?? null);
        el.style.cursor = n ? "pointer" : "";
      })
      .onNodeClick((n) => openRef.current((n as Node).id))
      .onEngineStop(() => g.zoomToFit(300, 24));
    const ro = new ResizeObserver(() => g.width(el.clientWidth || 300));
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
      className="relative overflow-hidden rounded-md bg-muted/30 outline-none focus-visible:ring-2 focus-visible:ring-ring"
      style={{ height: GRAPH_HEIGHT }}
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
