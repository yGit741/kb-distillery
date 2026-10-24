import createForceGraph, { type ForceGraphInstance, type LinkObject, type NodeObject } from "force-graph";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { GraphData } from "./graphData";
import type { SimLink, SimNode } from "./types";

export interface View {
  x: number;
  y: number;
  k: number;
}

export interface Forces {
  charge: number;
  linkDistance: number;
  gravity: number;
}

/** What the canvas asks of the host. All callbacks may change identity between renders. */
export interface ForceGraphProps {
  data: GraphData;
  forces: Forces;
  arrows: boolean;
  nodeRadius: (n: SimNode) => number;
  drawNode: (n: SimNode, ctx: CanvasRenderingContext2D, scale: number) => void;
  drawFramePost: (ctx: CanvasRenderingContext2D, scale: number) => void;
  drawLinkAfter: (l: SimLink, ctx: CanvasRenderingContext2D, scale: number) => void;
  linkColor: (l: SimLink) => string;
  linkWidth: (l: SimLink) => number;
  linkLabel: (l: SimLink) => string;
  onNodeHover: (n: SimNode | null) => void;
  onNodeClick: (n: SimNode, ev: MouseEvent) => void;
  onLinkClick: (ev: MouseEvent) => void;
  onBackgroundClick: (ev: MouseEvent) => void;
  onZoom: (k: number) => void;
  onEngineStop: () => void;
}

export interface ForceGraphHandle {
  nodes(): SimNode[];
  zoom(): number;
  center(): { x: number; y: number };
  setView(v: View, ms?: number): void;
  zoomBy(factor: number, ms?: number): void;
  zoomAt(factor: number, clientX: number, clientY: number): void;
  panBy(dx: number, dy: number): void;
  centerOn(x: number, y: number, k?: number, ms?: number): void;
  fit(include?: (n: SimNode) => boolean, ms?: number): void;
  screenOf(n: { x?: number; y?: number }): { x: number; y: number } | null;
  reheat(): void;
  refresh(): void;
}

type Instance = ForceGraphInstance & { refresh?: () => unknown };

const asSim = (n: NodeObject | null) => n as SimNode | null;
const asLink = (l: LinkObject) => l as unknown as SimLink;

/** Pixel deltas of a wheel event whatever its deltaMode. */
export function wheelUnits(ev: WheelEvent, pageHeight: number): { dx: number; dy: number } {
  const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? pageHeight : 1;
  return { dx: ev.deltaX * unit, dy: ev.deltaY * unit };
}

/** The scheme: wheel and two-finger scroll pan, pinch (ctrl+wheel) or Cmd+wheel zoom, shift+wheel pans sideways. */
export function wheelAction(ev: Pick<WheelEvent, "ctrlKey" | "metaKey" | "shiftKey">, dx: number, dy: number) {
  if (ev.ctrlKey || ev.metaKey) {
    // a pinch arrives as ctrl+wheel with small deltas, a Cmd+mouse wheel as +-100 steps
    const step = Math.max(-60, Math.min(60, dy));
    return { kind: "zoom" as const, factor: Math.exp(-step * (ev.ctrlKey ? 0.012 : 0.004)) };
  }
  if (ev.shiftKey && !dx) return { kind: "pan" as const, dx: dy, dy: 0 };
  return { kind: "pan" as const, dx, dy };
}

/**
 * Thin React wrapper over force-graph. It owns the canvas (inside its own div: force-graph empties
 * its container, so overlays are siblings) and nothing else. No pointer capture and no overlay takes
 * pointer events during a gesture, or force-graph misses the pointerup and stops reporting hovers.
 */
export const ForceGraph = forwardRef<ForceGraphHandle, ForceGraphProps & { className?: string }>(function ForceGraph(
  props,
  ref,
) {
  const host = useRef<HTMLDivElement>(null);
  const fg = useRef<Instance | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const ops = useRef<{ zoomAt: (f: number, x: number, y: number) => void; panBy: (dx: number, dy: number) => void }>({
    zoomAt: () => {},
    panBy: () => {},
  });

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const g: Instance = createForceGraph()(el);
    fg.current = g;
    g.backgroundColor("rgba(0,0,0,0)")
      .nodeId("id")
      .nodeLabel(() => "")
      .linkLineDash((l) => (asLink(l as LinkObject).kind === "shared" ? [2, 2] : null))
      .linkCanvasObjectMode((l) => (asLink(l as LinkObject).kind === "shared" ? "after" : undefined as unknown as string))
      .linkDirectionalParticles(0)
      .cooldownTicks(120)
      .nodeCanvasObjectMode(() => "replace")
      .enableNodeDrag(true)
      .enablePanInteraction(true)
      .enableZoomInteraction(false)
      .nodeVal((n) => latest.current.nodeRadius(n as SimNode) ** 2)
      .nodeRelSize(1)
      .nodeCanvasObject((n, ctx, s) => latest.current.drawNode(n as SimNode, ctx, s))
      .nodePointerAreaPaint((n, color, ctx) => {
        const node = n as SimNode;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(node.x ?? 0, node.y ?? 0, latest.current.nodeRadius(node), 0, 2 * Math.PI);
        ctx.fill();
      })
      .linkColor((l) => latest.current.linkColor(asLink(l)))
      .linkWidth((l) => latest.current.linkWidth(asLink(l)))
      .linkLabel((l) => latest.current.linkLabel(asLink(l)))
      .linkCanvasObject((l, ctx, s) => latest.current.drawLinkAfter(asLink(l), ctx, s))
      .linkDirectionalArrowRelPos(0.85)
      .onNodeHover((n) => latest.current.onNodeHover(asSim(n)))
      .onNodeClick((n, ev) => latest.current.onNodeClick(n as SimNode, ev))
      .onLinkClick((_l, ev) => latest.current.onLinkClick(ev))
      .onBackgroundClick((ev) => latest.current.onBackgroundClick(ev))
      .onRenderFramePost((ctx, s) => latest.current.drawFramePost(ctx, s))
      .onZoom((t) => latest.current.onZoom(t.k))
      .onEngineStop(() => latest.current.onEngineStop());

    const resize = () => g.width(el.clientWidth).height(el.clientHeight);
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    const wheel = (ev: WheelEvent) => {
      ev.preventDefault();
      const { dx, dy } = wheelUnits(ev, el.clientHeight);
      const a = wheelAction(ev, dx, dy);
      if (a.kind === "zoom") zoomAt(a.factor, ev.clientX, ev.clientY);
      else panBy(a.dx, a.dy);
    };
    // d3-zoom zooms in on a double-click; here a double-click opens the side reader instead
    const noDbl = (ev: Event) => ev.stopPropagation();
    el.addEventListener("wheel", wheel, { passive: false });
    el.addEventListener("dblclick", noDbl, true);

    function zoomAt(factor: number, cx: number, cy: number) {
      const k0 = g.zoom();
      const c = g.centerAt();
      const k = Math.min(Math.max(k0 * factor, 0.04), 24);
      const r = el!.getBoundingClientRect();
      const p = g.screen2GraphCoords(cx - r.left, cy - r.top);
      const f = k / k0;
      g.zoom(k, 0);
      g.centerAt(p.x - (p.x - c.x) / f, p.y - (p.y - c.y) / f, 0);
    }
    function panBy(dx: number, dy: number) {
      const c = g.centerAt();
      const k = g.zoom();
      g.centerAt(c.x + dx / k, c.y + dy / k, 0);
    }
    ops.current = { zoomAt, panBy };

    return () => {
      ro.disconnect();
      el.removeEventListener("wheel", wheel);
      el.removeEventListener("dblclick", noDbl, true);
      g._destructor();
      fg.current = null;
    };
  }, []);

  // data: nodes keep their coordinates (the host merged them); a new array restarts the layout gently
  useEffect(() => {
    fg.current?.graphData(props.data as unknown as { nodes: NodeObject[]; links: LinkObject[] });
  }, [props.data]);

  useEffect(() => {
    const g = fg.current;
    if (!g) return;
    g.d3Force("charge")?.strength?.(props.forces.charge);
    g.d3Force("link")?.distance?.(props.forces.linkDistance);
    g.d3Force("center")?.strength?.(props.forces.gravity);
    g.d3ReheatSimulation();
  }, [props.forces.charge, props.forces.linkDistance, props.forces.gravity]);

  useEffect(() => {
    fg.current?.linkDirectionalArrowLength(props.arrows ? 4 : 0);
  }, [props.arrows]);

  useImperativeHandle(
    ref,
    () => {
      const g = () => fg.current;
      return {
        nodes: () => (g()?.graphData().nodes ?? []) as SimNode[],
        zoom: () => g()?.zoom() ?? 1,
        center: () => g()?.centerAt() ?? { x: 0, y: 0 },
        setView: (v, ms = 0) => {
          g()?.centerAt(v.x, v.y, ms);
          g()?.zoom(v.k, ms);
        },
        zoomBy: (f, ms = 200) => {
          const inst = g();
          if (inst) inst.zoom(inst.zoom() * f, ms);
        },
        zoomAt: (f, x, y) => ops.current.zoomAt(f, x, y),
        panBy: (dx, dy) => ops.current.panBy(dx, dy),
        centerOn: (x, y, k, ms = 600) => {
          const inst = g();
          if (!inst) return;
          inst.centerAt(x, y, ms);
          if (k !== undefined) inst.zoom(k, ms);
        },
        fit: (include, ms = 400) => {
          // generous padding on a desktop, tight on a phone (a quarter of the width would be nothing but margin)
          const pad = Math.round(Math.min(90, Math.max(24, (host.current?.clientWidth ?? 800) * 0.08)));
          g()?.zoomToFit(ms, pad, include ? (n) => include(n as SimNode) : undefined);
        },
        screenOf: (n) => {
          const inst = g();
          const r = host.current?.getBoundingClientRect();
          if (!inst || !r || n.x == null || n.y == null || !Number.isFinite(n.x) || !Number.isFinite(n.y)) return null;
          const p = inst.graph2ScreenCoords(n.x, n.y);
          return { x: p.x + r.left, y: p.y + r.top };
        },
        reheat: () => void g()?.d3ReheatSimulation(),
        refresh: () => {
          const inst = g();
          if (inst?.refresh) inst.refresh();
        },
      };
    },
    [],
  );

  return <div ref={host} className={props.className} data-testid="force-graph" />;
});
