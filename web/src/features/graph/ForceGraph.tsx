import createForceGraph, { type ForceGraphInstance, type LinkObject, type NodeObject } from "force-graph";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { fitFrame } from "./fitFrame";
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

/** Pull each node toward a point (its theme's anchor), or leave it alone when `target` returns null. */
export interface Anchor {
  target: (n: SimNode) => readonly [number, number] | null;
  strength: number;
}

/** What the canvas asks of the host. All callbacks may change identity between renders. */
export interface ForceGraphProps {
  data: GraphData;
  forces: Forces;
  arrows: boolean;
  nodeRadius: (n: SimNode) => number;
  drawNode: (n: SimNode, ctx: CanvasRenderingContext2D, scale: number) => void;
  drawFramePost: (ctx: CanvasRenderingContext2D, scale: number) => void;
  /** Drawn under the nodes and links (region hulls). */
  drawFramePre?: (ctx: CanvasRenderingContext2D, scale: number) => void;
  /** null = no anchoring force. */
  anchor?: Anchor | null;
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
  /** Frame the given pages inside the canvas minus `left` px on its left side (a panel lies over that strip) and `top` px on its top (the search line). False when they have no place yet. */
  fitIn(include: (n: SimNode) => boolean, left: number, ms?: number, pad?: number, top?: number): boolean;
  screenOf(n: { x?: number; y?: number }): { x: number; y: number } | null;
  reheat(): void;
  refresh(): void;
  /** push the nodes around a screen point apart, gently, for about a second; the layout then settles and stays */
  spreadAt(clientX: number, clientY: number, radiusPx?: number): void;
}

/** The "spread here" force: a radial push from a point that fades over `ms`; nothing when no spread is active. */
interface Spread {
  x: number;
  y: number;
  /** reach in graph units */
  r: number;
  t0: number;
  ms: number;
}

type Instance = ForceGraphInstance & { refresh?: () => unknown };

/** The layout counts as settled below this alpha; d3's default decay reaches it in about 300 ticks. */
export const ALPHA_MIN = 0.001;
export const WARMUP_TICKS = 400;

const prefersReducedMotion = () =>
  typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Restart the layout: animated, or settled at once (off screen) when the viewer asked for reduced motion. */
function reheat(g: Instance) {
  // setting the same nodes again re-runs the off-screen warm-up from their current places
  if (prefersReducedMotion()) g.warmupTicks(WARMUP_TICKS).graphData({ ...g.graphData() });
  else g.d3ReheatSimulation();
}

const asSim = (n: NodeObject | null) => n as SimNode | null;
const asLink = (l: LinkObject) => l as unknown as SimLink;

/** Pixel deltas of a wheel event whatever its deltaMode. */
export function wheelUnits(ev: WheelEvent, pageHeight: number): { dx: number; dy: number } {
  const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? pageHeight : 1;
  return { dx: ev.deltaX * unit, dy: ev.deltaY * unit };
}

/**
 * The scheme: the wheel zooms toward the cursor (pinch, ctrl+wheel, too); shift+wheel pans, sideways for a
 * vertical wheel. Dragging with the wheel pressed pans as well.
 */
export function wheelAction(ev: Pick<WheelEvent, "ctrlKey" | "metaKey" | "shiftKey">, dx: number, dy: number) {
  if (ev.shiftKey) return dx ? { kind: "pan" as const, dx, dy } : { kind: "pan" as const, dx: dy, dy: 0 };
  // a pinch arrives as ctrl+wheel with small deltas, a mouse wheel as +-100 steps
  const step = Math.max(-60, Math.min(60, dy));
  return { kind: "zoom" as const, factor: Math.exp(-step * (ev.ctrlKey ? 0.012 : 0.004)) };
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
  const spread = useRef<Spread | null>(null);
  /** pages that stayed through a data change, pinned until the engine stops (see the data effect) */
  const held = useRef<{ n: SimNode; x: number; y: number }[]>([]);
  /** Drop our holds, but never a pin someone else set since (the anchored layout pins topics on its ring). */
  const releaseHeld = () => {
    for (const h of held.current) if (h.n.fx === h.x && h.n.fy === h.y) h.n.fx = h.n.fy = undefined;
    held.current = [];
  };
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
      // new data is laid out off screen and first drawn settled (ui-principles §29: nothing moves unasked)
      .d3AlphaMin(ALPHA_MIN)
      .warmupTicks(WARMUP_TICKS)
      .cooldownTicks(120)
      .nodeCanvasObjectMode(() => "replace")
      .enableNodeDrag(true)
      // left-drag on the background pans; the box / lasso selection is a right-drag (tools/RegionOverlay)
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
      .onRenderFramePre((ctx, s) => latest.current.drawFramePre?.(ctx, s))
      .onZoom((t) => latest.current.onZoom(t.k))
      // dragging moves the dragged page only: force-graph warms the whole layout up while a node is dragged
      // (alphaTarget 0.3), which set every other page drifting
      .onNodeDrag(() => void (g as unknown as { d3AlphaTarget(t: number): unknown }).d3AlphaTarget(0))
      .onEngineStop(() => {
        releaseHeld();
        latest.current.onEngineStop();
      });

    // the anchor force reads the latest props each tick, so switching layouts needs no re-registration
    let simNodes: SimNode[] = [];
    const anchorForce = Object.assign(
      (alpha: number) => {
        const a = latest.current.anchor;
        if (!a) return;
        for (const n of simNodes) {
          const t = a.target(n);
          if (!t || n.x == null || n.y == null) continue;
          const m = n as SimNode & { vx?: number; vy?: number };
          m.vx = (m.vx ?? 0) + (t[0] - n.x) * a.strength * alpha;
          m.vy = (m.vy ?? 0) + (t[1] - n.y) * a.strength * alpha;
        }
      },
      { initialize: (ns: NodeObject[]) => void (simNodes = ns as SimNode[]) },
    );
    g.d3Force("anchor", anchorForce as unknown as Parameters<Instance["d3Force"]>[1]);
    // "spread here": nodes within reach get a push away from the point, strongest at the centre, fading with time
    let spreadNodes: SimNode[] = [];
    const spreadForce = Object.assign(
      (alpha: number) => {
        const s = spread.current;
        if (!s) return;
        const t = (performance.now() - s.t0) / s.ms;
        if (t >= 1) {
          spread.current = null;
          return;
        }
        const k = (1 - t) * 1.6;
        for (const n of spreadNodes) {
          if (n.x == null || n.y == null) continue;
          const dx = n.x - s.x;
          const dy = n.y - s.y;
          const d = Math.hypot(dx, dy) || 1e-3;
          if (d > s.r) continue;
          const push = ((1 - d / s.r) * k * alpha * s.r) / 6;
          const m = n as SimNode & { vx?: number; vy?: number };
          m.vx = (m.vx ?? 0) + (dx / d) * push;
          m.vy = (m.vy ?? 0) + (dy / d) * push;
        }
      },
      { initialize: (ns: NodeObject[]) => void (spreadNodes = ns as SimNode[]) },
    );
    g.d3Force("spread", spreadForce as unknown as Parameters<Instance["d3Force"]>[1]);

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
    // pressing the wheel (middle button) and moving pans; no pointer capture (see above)
    let pan: { id: number; x: number; y: number } | null = null;
    const panDown = (ev: PointerEvent) => {
      if (ev.button !== 1) return;
      ev.preventDefault(); // no autoscroll
      pan = { id: ev.pointerId, x: ev.clientX, y: ev.clientY };
    };
    const panMove = (ev: PointerEvent) => {
      if (!pan || ev.pointerId !== pan.id) return;
      panBy(pan.x - ev.clientX, pan.y - ev.clientY);
      pan = { ...pan, x: ev.clientX, y: ev.clientY };
    };
    const panUp = (ev: PointerEvent) => {
      if (pan && ev.pointerId === pan.id) pan = null;
    };
    const noAux = (ev: MouseEvent) => ev.button === 1 && ev.preventDefault();
    el.addEventListener("wheel", wheel, { passive: false });
    el.addEventListener("dblclick", noDbl, true);
    el.addEventListener("pointerdown", panDown, true);
    el.addEventListener("mousedown", noAux, true);
    window.addEventListener("pointermove", panMove, true);
    window.addEventListener("pointerup", panUp, true);
    window.addEventListener("pointercancel", panUp, true);

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
      el.removeEventListener("pointerdown", panDown, true);
      el.removeEventListener("mousedown", noAux, true);
      window.removeEventListener("pointermove", panMove, true);
      window.removeEventListener("pointerup", panUp, true);
      window.removeEventListener("pointercancel", panUp, true);
      g._destructor();
      fg.current = null;
    };
  }, []);

  // data: a first layout is settled off screen. A changed set (a filter) never moves the pages that stay: they are
  // held where they are (fx/fy) while only the newcomers are placed off screen, and released once the engine stops.
  // So the only thing that moves a drawn page is the user's hand (drag, spread, a layout or force change).
  useEffect(() => {
    const g = fg.current;
    if (!g) return;
    const nodes = props.data.nodes as SimNode[];
    // our own pins may have been carried into the new nodes (the engine hadn't stopped yet): drop them first
    const pins = new Map(held.current.map((h) => [h.n.id, h] as const));
    for (const m of nodes) {
      const h = pins.get(m.id);
      if (h && m.fx === h.x && m.fy === h.y) m.fx = m.fy = undefined;
    }
    releaseHeld();
    held.current = nodes.filter((n) => n.x != null && n.y != null && n.fx == null).map((n) => ({ n, x: n.x!, y: n.y! }));
    for (const h of held.current) {
      h.n.fx = h.x;
      h.n.fy = h.y;
    }
    // nothing new to place: no warm-up; the engine ticks out over held nodes and nothing moves
    g.warmupTicks(held.current.length === nodes.length ? 0 : WARMUP_TICKS);
    g.graphData(props.data as unknown as { nodes: NodeObject[]; links: LinkObject[] });
  }, [props.data]);

  // the forces are set before the first layout; only a changed value (the user's) restarts it. Compared by value,
  // so StrictMode's second mount run doesn't count as a change
  const forcesWere = useRef<string | null>(null);
  useEffect(() => {
    const g = fg.current;
    if (!g) return;
    g.d3Force("charge")?.strength?.(props.forces.charge);
    g.d3Force("link")?.distance?.(props.forces.linkDistance);
    g.d3Force("center")?.strength?.(props.forces.gravity);
    const now = `${props.forces.charge}|${props.forces.linkDistance}|${props.forces.gravity}`;
    if (forcesWere.current !== null && forcesWere.current !== now) {
      releaseHeld(); // an explicit command must move the held pages too
      reheat(g);
    }
    forcesWere.current = now;
  }, [props.forces.charge, props.forces.linkDistance, props.forces.gravity]);

  useEffect(() => {
    // a cites link always shows who cites whom; other links only with the Directional arrows setting (the accessor
    // reads each link's kind when it draws, so only the setting is a dependency)
    fg.current?.linkDirectionalArrowLength((l) => (props.arrows || asLink(l as LinkObject).kind === "cites" ? 4 : 0));
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
        fitIn: (include, left, ms = 600, pad = 72, top = pad) => {
          const inst = g();
          const el = host.current;
          if (!inst || !el?.clientWidth || !el.clientHeight) return false;
          const ns = (inst.graphData().nodes as SimNode[]).filter((n) => include(n));
          if (!ns.length || ns.some((n) => !Number.isFinite(n.x) || !Number.isFinite(n.y))) return false;
          const xs = ns.map((n) => n.x as number);
          const ys = ns.map((n) => n.y as number);
          const v = fitFrame({ x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) }, el.clientWidth, el.clientHeight, { left, top, pad });
          inst.centerAt(v.x, v.y, ms);
          inst.zoom(v.k, ms);
          return true;
        },
        screenOf: (n) => {
          const inst = g();
          const r = host.current?.getBoundingClientRect();
          if (!inst || !r || n.x == null || n.y == null || !Number.isFinite(n.x) || !Number.isFinite(n.y)) return null;
          const p = inst.graph2ScreenCoords(n.x, n.y);
          return { x: p.x + r.left, y: p.y + r.top };
        },
        reheat: () => {
          const inst = g();
          if (!inst) return;
          releaseHeld();
          reheat(inst);
        },
        spreadAt: (cx, cy, radiusPx = 160) => {
          const inst = g();
          const r = host.current?.getBoundingClientRect();
          if (!inst || !r) return;
          const p = inst.screen2GraphCoords(cx - r.left, cy - r.top);
          spread.current = { x: p.x, y: p.y, r: radiusPx / inst.zoom(), t0: performance.now(), ms: 1200 };
          releaseHeld();
          inst.d3ReheatSimulation();
        },
        refresh: () => {
          const inst = g();
          // force-graph 1.x has no public refresh: a zero-length zoom to the current scale flags its redraw
          if (inst?.refresh) inst.refresh();
          else if (inst) inst.zoom(inst.zoom());
        },
      };
    },
    [],
  );

  return <div ref={host} className={props.className} data-testid="force-graph" />;
});
