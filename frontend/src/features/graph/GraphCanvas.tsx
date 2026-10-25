import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import { useKb } from "@/lib/store";
import { cn } from "@/lib/utils";
import { useTheme } from "@/theme/theme";
import { readCanvasColors, withAlpha, type CanvasColors } from "./canvasTheme";
import { computeFocus, fadedLinkOpacity, fadedNodeOpacity, focusKey, nodeOpacity, type Focus } from "./focus";
import { ForceGraph, type Anchor, type ForceGraphHandle } from "./ForceGraph";
import { buildGraphData, edgeWeight, edgeWeights, largestComponent, type NeighborMap } from "./graphData";
import { createHoverIntent, createSpeedMeter, HOVER_TUNING } from "./hoverIntent";
import { drawArcs } from "./lab/arcs";
import { drawHulls, drawLabelLayer, type FadeState } from "./lab/draw";
import { useLabHud } from "./lab/hud";
import { hopsFrom, type Importance } from "./lab/importance";
import { FORCED } from "./lab/labelPlan";
import { areaNames } from "./lab/regions";
import { bubbleAim, drawBubble, magnetCursor, pickMagnetic, rgbOf, stepBubble, type Bubble, type ScreenNode } from "./magnet";
import { drawPile, formatOfPile, isPile, isPileId, pileRadius } from "./rawLayer";
import { DRAG_PX } from "./selection";
import { useGraphUi } from "./store";
import { useDecor } from "./tools/decor";
import { colorOf, drawMark, drawSourceGlyph, effectiveColorBy, layeredRadii, markOf, METRIC_COLORS, nodeRadius, personInitials, SOURCE_GLYPH_PX, type ColorBy, type SizeBy } from "./style";
import type { GNode, GraphModel, SimLink, SimNode } from "./types";

export interface CanvasHandle {
  screenOf: (id: string) => { x: number; y: number } | null;
  hovered: () => string | null;
  zoomBy: (factor: number) => void;
  reheat: () => void;
}

interface Props {
  model: GraphModel;
  byId: ReadonlyMap<string, GNode>;
  neighbors: NeighborMap;
  visible: ReadonlySet<string>;
  /** the importance score of the visible pages (lab/importance), shared with the rail */
  imp: Importance;
  className?: string;
  onOpenMenu: (id: string, x: number, y: number) => void;
  onBackgroundContext: () => void;
  onOpenReader: (id: string) => void;
  /** A pile of the data layer was clicked: open the files of that format. */
  onOpenPile?: (format: string) => void;
}

interface RenderState {
  colors: CanvasColors;
  imp: Importance;
  forced: Map<string, number>;
  hops: Map<string, number> | null;
  focus: Focus | null;
  /** the focus being faded out, with the fade's progress 0..1 (calm hover) */
  prevFocus: Focus | null;
  fadeT: number;
  selected: ReadonlySet<string>;
  /** the committed hover: drives the focus and hover labels (the pointer itself is `intent.pointed()`) */
  hover: string | null;
  /** pointer in CSS px of the canvas (the hover lens) */
  pointer: { x: number; y: number } | null;
}

const EMPTY_IMPORTANCE: Importance = { score: new Map(), terms: new Map(), qrank: new Map(), maxScore: 1 };

/** The 0..1 signal behind a size or colour mode that reads the importance score. */
function metricOf(imp: Importance, n: GNode, by: SizeBy | ColorBy): number {
  const t = imp.terms.get(n.id);
  if (!t) return 0;
  if (by === "evidence") return t.evidence;
  if (by === "gap") return t.gap;
  return (imp.score.get(n.id) ?? 0) / (imp.maxScore || 1);
}

/** Topics pinned on a ring, one per theme; their pages are pulled toward it (the anchored, map-like layout). */
function themeAnchors(nodes: readonly SimNode[], linkDistance: number): Map<string, readonly [number, number]> {
  const topics = nodes.filter((n) => n.type === "topic").sort((a, b) => a.id.localeCompare(b.id));
  const radius = (10 * Math.sqrt(nodes.length) + 60) * (linkDistance / 28);
  const out = new Map<string, readonly [number, number]>();
  topics.forEach((t, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, topics.length);
    const p = [radius * Math.cos(a), radius * Math.sin(a)] as const;
    t.fx = p[0];
    t.fy = p[1];
    if (t.areas[0] && !out.has(t.areas[0])) out.set(t.areas[0], p);
  });
  return out;
}

const endId = (e: string | SimNode) => (typeof e === "string" ? e : e.id);
const DOUBLE_MS = 380;

/**
 * The graph itself: force-graph plus the mouse scheme. Modeless: hover always labels a node and a click
 * labels its neighbours; the wheel pans, pinch or Cmd+wheel zooms; double-click opens the side reader;
 * right-click a node opens its menu. Box, lasso and path selection are tools (./tools), not here.
 */
export const GraphCanvas = forwardRef<CanvasHandle, Props>(function GraphCanvas(
  { model, byId, neighbors, visible, imp, className, onOpenMenu, onBackgroundContext, onOpenReader, onOpenPile },
  ref,
) {
  const ui = useGraphUi();
  const selection = useKb((s) => s.selection);
  const theme = useTheme((s) => s.theme);
  const fg = useRef<ForceGraphHandle>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const overlay = useRef<HTMLCanvasElement>(null);

  const rs = useRef<RenderState>({
    colors: readCanvasColors(),
    imp: EMPTY_IMPORTANCE,
    forced: new Map(),
    hops: null,
    focus: null,
    prevFocus: null,
    fadeT: 1,
    selected: new Set(),
    hover: null,
    pointer: null,
  });
  const k = useRef(1);
  const fades = useRef(new Map<string, FadeState>());
  const frame = useRef({ last: 0, churn: 0, hudAt: 0, raf: 0 });
  const pendingFit = useRef(true);
  const lastClick = useRef<{ id: string | null; at: number }>({ id: null, at: 0 });
  const pressed = useRef(false);
  const live = useRef({ ui, theme, selection, byId, neighbors, visible, onOpenReader, onOpenMenu, onBackgroundContext, onOpenPile });
  live.current = { ui, theme, selection, byId, neighbors, visible, onOpenReader, onOpenMenu, onBackgroundContext, onOpenPile };

  rs.current.imp = imp;
  const names = useMemo(() => areaNames(model.nodes), [model]);
  const initials = useMemo(() => personInitials(model.nodes), [model]);
  const weights = useMemo(() => edgeWeights(model), [model]);
  const weightsRef = useRef(weights);
  weightsRef.current = weights;
  const core = useMemo(() => largestComponent(visible, neighbors), [visible, neighbors]);
  const coreRef = useRef(core);
  coreRef.current = core;
  const radiusOpts = useMemo(
    () => ({
      by: ui.sizeBy,
      base: ui.nodeSize,
      range: ui.lab.nodeRange,
      perceptual: ui.lab.perceptual,
      metric: (n: GNode) => metricOf(rs.current.imp, n, ui.sizeBy),
    }),
    [ui.sizeBy, ui.nodeSize, ui.lab.nodeRange, ui.lab.perceptual, imp], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const radiusRef = useRef(radiusOpts);
  radiusRef.current = radiusOpts;
  // marks on: each layer sized on its own scale (./style layeredRadii), over the pages drawn
  const layered = useMemo(
    () => (ui.shapes ? layeredRadii(model.nodes.filter((n) => visible.has(n.id)), radiusOpts) : null),
    [ui.shapes, model, visible, radiusOpts],
  );
  const layeredRef = useRef(layered);
  layeredRef.current = layered;
  const radius = useCallback(
    (n: GNode) => (isPile(n) ? pileRadius(n) : (layeredRef.current?.get(n.id) ?? nodeRadius(n, radiusRef.current))),
    [],
  );

  // ---- calm hover: the rest of the graph cross-fades between foci instead of switching in one frame
  const fade = useRef({ key: "", at: 0, ms: 0, raf: 0 });
  const startFade = useCallback((prev: Focus | null, next: Focus | null, calm: boolean) => {
    const f = fade.current;
    const key = focusKey(next);
    if (key === f.key) return;
    f.key = key;
    const still = !calm || matchMedia("(prefers-reduced-motion: reduce)").matches;
    f.ms = still ? 0 : next ? HOVER_TUNING.fadeIn : HOVER_TUNING.fadeOut;
    // a fade interrupted midway starts from the current focus: the brief jump is far smaller than a flash
    rs.current.prevFocus = f.ms ? prev : null;
    rs.current.fadeT = f.ms ? 0 : 1;
    f.at = performance.now();
    const step = () => {
      const t = Math.min(1, (performance.now() - f.at) / (f.ms || 1));
      rs.current.fadeT = t;
      if (t >= 1) {
        rs.current.prevFocus = null;
        f.raf = 0;
      } else f.raf = requestAnimationFrame(step);
      fg.current?.refresh();
    };
    if (f.ms && !f.raf) f.raf = requestAnimationFrame(step);
  }, []);

  const recompute = useCallback(() => {
    const { ui: u, selection: sel, byId: ids, neighbors: nb, visible: vis } = live.current;
    const gone = intent.current?.pointed();
    if (gone && !vis.has(gone)) {   // filtered out or reloaded: nothing may act on it any more
      intent.current?.reset();
      wrap.current?.classList.remove("graph-pointer");
    }
    if (rs.current.hover && !vis.has(rs.current.hover)) rs.current.hover = null;
    const hover = rs.current.hover;
    if (useLabHud.getState().hover !== hover) useLabHud.setState({ hover });
    const cfg = u.lab;
    const score = rs.current.imp.score;
    rs.current.selected = sel;
    // focus by degree of interest: the selection's hops stay lit, the rest fades
    const hops = cfg.doiHops > 0 && sel.size ? hopsFrom(sel, vis, nb, cfg.doiHops) : null;
    rs.current.hops = hops;
    // a legend spotlight (a type chip under the pointer) is a focus on every drawn page of the type: same fade
    const spot = u.spotlight;
    const spotIds = spot ? new Set([...vis].filter((id) => spot.has(ids.get(id)?.type ?? ""))) : null;
    const next = spotIds ? { core: spotIds, lit: spotIds, dim: 0.15 } : hops ? { core: new Set(sel), lit: new Set(hops.keys()) } : computeFocus(sel, hover, nb, u.highlight);
    startFade(rs.current.focus, next, u.calmHover);
    rs.current.focus = next;
    // forced labels: hovered page, the selection, their best neighbours (capped), every page of an "Aa" type
    const forced = new Map<string, number>();
    const put = (id: string, r: number) => {
      const cur = forced.get(id);
      if (vis.has(id) && (cur === undefined || cur > r)) forced.set(id, r);
    };
    // hover neighbours rank by score; a click's by edge weight (then score), so the same page always lights the same ones
    const byScore = (a: string, b: string) => (score.get(b) ?? 0) - (score.get(a) ?? 0) || a.localeCompare(b);
    const byWeight = (id: string) => (a: string, b: string) => edgeWeight(weightsRef.current, id, b) - edgeWeight(weightsRef.current, id, a) || byScore(a, b);
    const topNeighbours = (id: string, cmp = byScore) => [...new Set(nb.get(id) ?? [])].filter((j) => vis.has(j)).sort(cmp).slice(0, cfg.neighborCap);
    if (hover) {
      put(hover, FORCED.hover);
      if (cfg.hoverNeighbors) topNeighbours(hover).forEach((j) => put(j, FORCED.near));
    }
    for (const id of sel) {
      put(id, FORCED.selected);
      topNeighbours(id, cfg.neighborBy === "weight" ? byWeight(id) : byScore).forEach((j) => put(j, FORCED.near));
    }
    if (u.typeLabels.size) for (const id of vis) if (u.typeLabels.has(ids.get(id)?.type ?? "")) put(id, FORCED.type);
    // a spotlit type small enough to label whole (people, topics) gets every label; a big one keeps the budget
    if (spotIds && spotIds.size <= 40) for (const id of spotIds) put(id, FORCED.type);
    rs.current.forced = forced;
    fg.current?.refresh();
  }, [startFade]);

  // What the pointer is on follows it at once (cursor, clicks, drags, the bubble); the focus commits
  // through the hover intent once the pointer settles (./hoverIntent).
  const speed = useRef(createSpeedMeter());
  const intent = useRef<ReturnType<typeof createHoverIntent> | null>(null);
  intent.current ??= createHoverIntent({
    commit: (id) => {
      rs.current.hover = id;
      recompute();
    },
    committed: () => rs.current.hover,
    speed: () => speed.current.speed(performance.now()),
    enabled: () => live.current.ui.calmHover,
  });
  const pointed = useCallback(() => intent.current?.pointed() ?? null, []);
  const setHover = useCallback((id: string | null) => {
    if (intent.current?.pointed() === id) return;
    wrap.current?.classList.toggle("graph-pointer", id !== null);
    intent.current?.request(id);
    fg.current?.refresh(); // the ring follows the pointer at once
  }, []);
  useEffect(() => {
    if (!ui.calmHover) intent.current?.flush();
  }, [ui.calmHover]);
  useEffect(
    () => () => {
      intent.current?.cancel();
      cancelAnimationFrame(fade.current.raf);
      fade.current.raf = 0;
    },
    [],
  );

  // ---- data: positions of nodes that stay are carried over
  const data = useMemo(() => {
    const prev = new Map(fg.current?.nodes().map((n) => [n.id, { x: n.x, y: n.y, fx: n.fx, fy: n.fy }]) ?? []);
    return buildGraphData(model, visible, prev);
  }, [model, visible]);

  // the anchored layout pins topics on a ring and pulls every page toward its theme; free unpins them
  const anchors = useMemo(() => {
    const nodes = data.nodes as SimNode[];
    if (ui.layoutMode !== "anchored") {
      for (const n of nodes) if (n.type === "topic") n.fx = n.fy = undefined;
      return null;
    }
    return themeAnchors(nodes, ui.linkDistance);
  }, [data, ui.layoutMode, ui.linkDistance]);
  const anchor = useMemo<Anchor | null>(
    () =>
      anchors
        ? {
            strength: ui.areaPull,
            target: (n) => {
              const a = n.type === "topic" ? undefined : anchors.get(n.areas?.[0] ?? "");
              return a ? [a[0] * 0.75, a[1] * 0.75] : null;
            },
          }
        : null,
    [anchors, ui.areaPull],
  );
  useEffect(() => {
    fg.current?.reheat();
  }, [ui.layoutMode, ui.areaPull]);

  // ---- tool decor (experiment halos, faded links) is read at draw time; a change only needs a redraw
  useEffect(() => useDecor.subscribe(() => fg.current?.refresh()), []);

  // ---- redraw when anything the draw reads changes
  useEffect(() => {
    rs.current.colors = readCanvasColors();
    recompute();
  }, [recompute, theme, visible, selection, byId, neighbors, ui.highlight, ui.lab, ui.typeLabels, ui.spotlight, ui.colorBy, ui.shapes, ui.linkOpacity, radiusOpts, layered, imp]);

  // a changed set of pages is refitted once the layout settles (or after a moment if it never reports it)
  useEffect(() => {
    pendingFit.current = true;
    const t = window.setTimeout(() => {
      if (!pendingFit.current) return;
      pendingFit.current = false;
      fitRef.current();
    }, 1600);
    return () => window.clearTimeout(t);
  }, [ui.shownTypes, ui.shownDepths, ui.view]);

  // ---- fit (largest connected component: stray islands drift far out and would shrink everything)
  const fit = useCallback(() => {
    const core = largestComponent(live.current.visible, live.current.neighbors);
    fg.current?.fit(core.size > 1 ? (n) => core.has(n.id) || isPile(n) : undefined, 400);
    window.setTimeout(() => {
      k.current = fg.current?.zoom() ?? 1;
      recompute();
    }, 450);
  }, [recompute]);

  const fitRef = useRef(fit);
  fitRef.current = fit;
  useEffect(() => {
    if (ui.fitTick > 0) fit();
  }, [ui.fitTick, fit]);

  // ---- pending focus: wait for the page to be drawn and laid out, then centre on it
  useEffect(() => {
    const req = ui.focusRequest;
    if (!req) return;
    const node = byId.get(req.id);
    if (!node) {
      useGraphUi.setState({ focusRequest: null });
      return;
    }
    if (!visible.has(req.id)) {
      useGraphUi.setState({ revealed: new Set([...live.current.ui.revealed, req.id]) });
      return;
    }
    let tries = 0;
    let timer = 0;
    const attempt = () => {
      const n = fg.current?.nodes().find((m) => m.id === req.id);
      if (n && Number.isFinite(n.x) && Number.isFinite(n.y)) {
        useKb.getState().setSelection([req.id]);
        fg.current?.centerOn(n.x as number, n.y as number, req.zoom && k.current < 1.6 ? 2.2 : undefined, 600);
        useGraphUi.setState({ focusRequest: null });
      } else if (tries++ < 40) {
        timer = window.setTimeout(attempt, 100);
      } else {
        useGraphUi.setState({ focusRequest: null });
      }
    };
    attempt();
    return () => window.clearTimeout(timer);
  }, [ui.focusRequest, byId, visible, data]);

  // ---- the magnetic pointer: nearest page within its own reach
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    let queued = false;
    let last: { x: number; y: number } | null = null;
    const screenNodes = (): ScreenNode[] => {
      const g = fg.current;
      if (!g) return [];
      const scale = g.zoom();
      const list: ScreenNode[] = [];
      for (const n of g.nodes()) {
        const s = g.screenOf(n);
        if (s) list.push({ id: n.id, x: s.x, y: s.y, r: radius(n) * scale });
      }
      return list;
    };
    const retarget = () => {
      queued = false;
      if (!fg.current || !last || !live.current.ui.magnet || pressed.current) return;
      setHover(pickMagnetic(screenNodes(), last.x, last.y, pointed()));
      kick();
    };

    // the soft bubble joining pointer and target, on a canvas laid over the graph
    el.style.setProperty("--magnet-cursor", magnetCursor());
    let bubble: Bubble = { r: 0, a: 0 };
    let raf = 0;
    let recheckAt = 0;
    const paint = () => {
      raf = 0;
      const cv = overlay.current;
      const ctx = cv?.getContext("2d");
      if (!cv || !ctx) return;
      const dpr = window.devicePixelRatio || 1;
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const aim = !!last && live.current.ui.magnet && !pressed.current;
      // the layout can drift under a pointer that holds still: re-check the target a few times a second
      const now = performance.now();
      if (aim && last && now - recheckAt > 150) {
        recheckAt = now;
        setHover(pickMagnetic(screenNodes(), last.x, last.y, pointed()));
      }
      const list = aim ? screenNodes() : [];
      const t = list.find((n) => n.id === pointed()) ?? null;
      const { want, strength } = t && last ? bubbleAim(t, last.x, last.y, list) : { want: 0, strength: 0 };
      bubble = stepBubble(bubble, want, strength, matchMedia("(prefers-reduced-motion: reduce)").matches);
      const p = rs.current.pointer;
      if (p) {
        const box = el.getBoundingClientRect();
        const rgb = rgbOf(getComputedStyle(document.documentElement).getPropertyValue("--primary"));
        drawBubble(ctx, p.x, p.y, t && { ...t, x: t.x - box.left, y: t.y - box.top }, bubble, rgb);
      }
      if (t || bubble.a > 0.02) raf = requestAnimationFrame(paint);
    };
    const kick = () => {
      if (!raf) raf = requestAnimationFrame(paint);
    };
    const move = (e: PointerEvent) => {
      last = { x: e.clientX, y: e.clientY };
      speed.current.note(e.clientX, e.clientY, performance.now());
      const r = el.getBoundingClientRect();
      rs.current.pointer = { x: e.clientX - r.left, y: e.clientY - r.top };
      if (live.current.ui.lab.lens) fg.current?.refresh();
      if (!live.current.ui.magnet || queued) return;
      queued = true;
      requestAnimationFrame(retarget);
    };
    const leave = () => {
      last = null;
      rs.current.pointer = null;
      if (live.current.ui.magnet) setHover(null);
      kick();
    };
    const down = (e: PointerEvent) => {
      if (e.button === 0) pressed.current = true;
      kick();
    };
    const up = () => {
      if (!pressed.current) return;
      pressed.current = false;
      requestAnimationFrame(retarget);
    };
    // the view moved under the pointer
    const wheel = () => requestAnimationFrame(retarget);
    el.addEventListener("pointermove", move, { passive: true });
    el.addEventListener("pointerleave", leave);
    el.addEventListener("pointerdown", down, true);
    window.addEventListener("pointerup", up);
    el.addEventListener("wheel", wheel, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("wheel", wheel);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
      el.removeEventListener("pointerdown", down, true);
      window.removeEventListener("pointerup", up);
    };
  }, [radius, setHover, pointed]);

  // ---- right-click: a node opens its menu, empty space closes the panels and drops the selection.
  // A right-drag is the box / lasso selection (tools/RegionOverlay), so the click is decided on release:
  // some systems fire `contextmenu` on press. Without a pressed right button (keyboard, long-press) it acts at once.
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    let press: { x: number; y: number; id: number; node: string | null; moved: boolean } | null = null;
    const act = (x: number, y: number, node: string | null) => {
      if (node && !isPileId(node)) live.current.onOpenMenu(node, x, y);
      else if (!node) live.current.onBackgroundContext();
    };
    let released = -Infinity;
    const ctx = (e: MouseEvent) => {
      e.preventDefault();
      // Windows and Linux fire `contextmenu` just after the release that already acted (or ended a drag)
      if (!press && e.timeStamp - released > 150) act(e.clientX, e.clientY, pointed());
    };
    const down = (e: PointerEvent) => {
      if (e.button === 2) press = { x: e.clientX, y: e.clientY, id: e.pointerId, node: pointed(), moved: false };
    };
    const move = (e: PointerEvent) => {
      if (press && e.pointerId === press.id && Math.hypot(e.clientX - press.x, e.clientY - press.y) >= DRAG_PX) press.moved = true;
    };
    const up = (e: PointerEvent) => {
      if (!press || e.pointerId !== press.id) return;
      const p = press;
      press = null;
      released = e.timeStamp;
      if (e.type === "pointerup" && !p.moved) act(e.clientX, e.clientY, p.node);
    };
    el.addEventListener("contextmenu", ctx);
    el.addEventListener("pointerdown", down, true);
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", up, true);
    window.addEventListener("pointercancel", up, true);
    return () => {
      el.removeEventListener("contextmenu", ctx);
      el.removeEventListener("pointerdown", down, true);
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", up, true);
      window.removeEventListener("pointercancel", up, true);
    };
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      screenOf: (id) => {
        const n = fg.current?.nodes().find((m) => m.id === id);
        return n ? fg.current?.screenOf(n) ?? null : null;
      },
      hovered: pointed,
      zoomBy: (f) => fg.current?.zoomBy(f),
      reheat: () => fg.current?.reheat(),
    }),
    [],
  );

  // ---- clicks
  const clickNode = useCallback(
    (id: string, ev: MouseEvent) => {
      if (isPileId(id)) {
        live.current.onOpenPile?.(formatOfPile(id));
        return;
      }
      const now = Date.now();
      const last = lastClick.current;
      if (last.id === id && now - last.at < DOUBLE_MS) {
        lastClick.current = { id: null, at: 0 };
        live.current.onOpenReader(id);
        return;
      }
      lastClick.current = { id, at: now };
      const kb = useKb.getState();
      if (ev.shiftKey || ev.metaKey || ev.ctrlKey) kb.toggle(id);
      else kb.setSelection([id]);
    },
    [],
  );

  const onNodeClick = useCallback((n: SimNode, ev: MouseEvent) => clickNode(n.id, ev), [clickNode]);
  // with the magnet a near miss can land on an edge or the background: that click belongs to the pulled node
  const onNearMiss = useCallback(
    (ev: MouseEvent) => {
      const id = pointed();
      if (live.current.ui.magnet && id) {
        clickNode(id, ev);
        return;
      }
      if (!ev.shiftKey && !ev.metaKey && !ev.ctrlKey) useKb.getState().clearSelection();
    },
    [clickNode],
  );

  // ---- drawing
  const drawNode = useCallback(
    (n: SimNode, ctx: CanvasRenderingContext2D, scale: number) => {
      const { colors, focus, selected } = rs.current;
      // the ring follows the pointer at once (small, local feedback); dim and labels wait for the intent
      const hover = intent.current?.pointed() ?? null;
      if (n.x == null || n.y == null) return;
      if (isPile(n)) {
        drawPile(n, ctx, scale, colors, hover === n.id);
        return;
      }
      // a spotlit type (legend hover) is drawn a third larger as well as lit
      const r = radius(n) * (live.current.ui.spotlight?.has(n.type) ? 1.3 : 1);
      const alpha = fadedNodeOpacity(n.id, focus, rs.current.prevFocus, rs.current.fadeT);
      const isSel = selected.has(n.id);
      const halo = useDecor.getState().halo?.get(n.id);
      if (halo) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + (2 + 4 * halo) / scale, 0, 2 * Math.PI);
        ctx.fillStyle = withAlpha(colors.warn, 0.15 + 0.55 * halo);
        ctx.fill();
      }
      if (isSel || hover === n.id) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 3 / scale, 0, 2 * Math.PI);
        ctx.strokeStyle = withAlpha(colors.ring, isSel ? 0.95 : 0.55);
        ctx.lineWidth = (isSel ? 2 : 1.5) / scale;
        ctx.stroke();
      }
      const shapes = live.current.ui.shapes;
      const by = effectiveColorBy(live.current.ui.colorBy, shapes);
      // marks on: an ordered colouring is a neutral ramp (lightness), so it never fights the area hulls
      const col = colorOf(n, by, METRIC_COLORS.has(by) ? metricOf(rs.current.imp, n, by) : undefined, shapes ? live.current.theme : null);
      if (shapes) {
        // one mark per type, the same at every zoom; never under 5 px on screen
        ctx.globalAlpha = alpha;
        const rd = Math.max(r, 5 / scale);
        const mark = markOf(n.type);
        drawMark(ctx, mark, n.x, n.y, rd, col, colors.background, colors.font, initials.get(n.id));
        // a source is a plain dot until it is big enough on screen (zoom) or under the pointer: then its type glyph
        if (mark === "source" && (rd * scale >= SOURCE_GLYPH_PX || hover === n.id)) drawSourceGlyph(ctx, n.type, n.x, n.y, rd);
        ctx.globalAlpha = 1;
        return;
      }
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.globalAlpha = alpha;
      if (n.type === "question") {
        // a question is a hollow ring with a "?" inside: readable without a label
        ctx.fillStyle = colors.background;
        ctx.fill();
        ctx.strokeStyle = col;
        ctx.lineWidth = r * 0.22;
        ctx.stroke();
        ctx.fillStyle = col;
        ctx.font = `600 ${r * 1.4}px ${colors.font}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("?", n.x, n.y + r * 0.08);
        ctx.globalAlpha = 1;
        return;
      }
      ctx.fillStyle = col;
      ctx.fill();
      ctx.globalAlpha = alpha * 0.5;
      ctx.strokeStyle = colors.background;
      ctx.lineWidth = 0.8 / scale;
      ctx.stroke();
      ctx.globalAlpha = 1;
    },
    [radius, initials],
  );

  const drawFramePre = useCallback(
    (ctx: CanvasRenderingContext2D, scale: number) => {
      const g = fg.current;
      if (!g) return;
      const arcs = useDecor.getState().arcs;
      if (arcs?.length) drawArcs(ctx, g.nodes(), arcs, scale, rs.current.colors);
      const u = live.current.ui;
      // marks on: hulls say where (area tints) and show only when the nodes do not already say it with their colour
      const hulls = u.shapes ? effectiveColorBy(u.colorBy, u.shapes) !== "area" : u.lab.hulls;
      if (hulls) drawHulls(ctx, g.nodes().filter((n) => !isPile(n)), scale, names, u.lab.hullSigma);
    },
    [names],
  );

  const drawFramePost = useCallback(
    (ctx: CanvasRenderingContext2D) => {
      const g = fg.current;
      const el = wrap.current;
      if (!g || !el) return;
      const { colors, focus, hover, imp: score, forced, hops, pointer } = rs.current;
      const now = performance.now();
      const f = frame.current;
      const dt = f.last ? Math.min(100, now - f.last) : 16;
      f.last = now;
      const cfg = live.current.ui.lab;
      const res = drawLabelLayer({
        ctx,
        nodes: g.nodes().filter((n) => !isPile(n)),
        fitIds: coreRef.current,
        width: el.clientWidth,
        height: el.clientHeight,
        cfg,
        imp: score,
        forced,
        hops,
        dim: (id) => nodeOpacity(id, focus) < 0.5,
        radius,
        colors,
        areaNames: names,
        fades: fades.current,
        pointer: cfg.lens ? pointer : null,
        hovered: hover,
        dt,
        nodeColor: (n) => {
          const u = live.current.ui;
          const by = effectiveColorBy(u.colorBy, u.shapes);
          return colorOf(n, by, METRIC_COLORS.has(by) ? metricOf(rs.current.imp, n, by) : undefined, u.shapes ? live.current.theme : null);
        },
      });
      f.churn = f.churn * 0.9 + res.changes * (1000 / Math.max(16, dt)) * 0.1;
      if (now - f.hudAt > 250) {
        f.hudAt = now;
        const vis = live.current.visible;
        const byIdNow = live.current.byId;
        let conceptsVisible = 0;
        for (const id of vis) if (byIdNow.get(id)?.layer === "concept") conceptsVisible++;
        const onScreenLabels = res.plan.placed.filter((p) => p.box[2] > 0 && p.box[0] < el.clientWidth && p.box[3] > 0 && p.box[1] < el.clientHeight);
        useLabHud.getState().set({
          zoom: res.zr,
          labels: res.plan.shownOnScreen,
          onScreen: res.plan.onScreen,
          concepts: onScreenLabels.filter((p) => p.n.layer === "concept").length,
          conceptsVisible,
          coverage: res.plan.coverage,
          dropped: res.plan.dropped,
          churn: f.churn,
          minPx: res.plan.minPx,
        });
      }
      // fades and the churn readout need frames even when force-graph would pause its redraw
      if ((res.animating || f.churn > 0.2) && !f.raf) {
        f.raf = requestAnimationFrame(() => {
          f.raf = 0;
          fg.current?.refresh();
        });
      }
    },
    [radius, names],
  );

  const drawLinkAfter = useCallback((l: SimLink, ctx: CanvasRenderingContext2D, scale: number) => {
    if (l.kind !== "shared" || scale < 1.6) return;
    const a = l.source as SimNode;
    const b = l.target as SimNode;
    if (typeof a === "string" || typeof b === "string" || a.x == null || b.x == null || a.y == null || b.y == null) return;
    ctx.save();
    ctx.font = `${Math.max(2.5, 9 / scale)}px ${rs.current.colors.font}`;
    ctx.fillStyle = rs.current.colors.muted;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(l.shared ?? 1), (a.x + b.x) / 2, (a.y + b.y) / 2);
    ctx.restore();
  }, []);

  const linkColor = useCallback((l: SimLink) => {
    const { focus, prevFocus, fadeT, colors } = rs.current;
    const a = endId(l.source);
    const b = endId(l.target);
    const fade = useDecor.getState().linkFade?.(a, b) ?? 1;
    return withAlpha(colors.link, fade * fadedLinkOpacity(a, b, focus, prevFocus, fadeT, live.current.ui.linkOpacity, l.kind));
  }, []);
  const linkWidth = useCallback((l: SimLink) => (l.kind === "shared" ? 0.35 + Math.min(l.shared ?? 1, 6) * 0.1 : 0.8), []);
  const linkLabel = useCallback(
    (l: SimLink) => (l.kind === "shared" ? `${l.shared} shared source${l.shared === 1 ? "" : "s"}` : ""),
    [],
  );

  const onZoom = useCallback((z: number) => {
    k.current = z;
  }, []);

  const onEngineStop = useCallback(() => {
    if (!pendingFit.current) return;
    pendingFit.current = false;
    fit();
  }, [fit]);

  const onNodeHover = useCallback(
    (n: SimNode | null) => {
      if (live.current.ui.magnet) return;
      setHover(n ? n.id : null);
    },
    [setHover],
  );

  return (
    <div
      ref={wrap}
      className={cn(
        "relative size-full [&.graph-pointer_canvas]:cursor-pointer",
        ui.magnet && "[&:not(.graph-pointer)_canvas]:[cursor:var(--magnet-cursor,default)]",
        className,
      )}
    >
      <ForceGraph
        ref={fg}
        className="size-full"
        data={data}
        forces={{ charge: ui.charge, linkDistance: ui.linkDistance, gravity: ui.gravity }}
        arrows={ui.arrows}
        nodeRadius={radius}
        drawNode={drawNode}
        drawFramePost={drawFramePost}
        drawFramePre={drawFramePre}
        anchor={anchor}
        drawLinkAfter={drawLinkAfter}
        linkColor={linkColor}
        linkWidth={linkWidth}
        linkLabel={linkLabel}
        onNodeHover={onNodeHover}
        onNodeClick={onNodeClick}
        onLinkClick={onNearMiss}
        onBackgroundClick={onNearMiss}
        onZoom={onZoom}
        onEngineStop={onEngineStop}
      />
      <canvas ref={overlay} aria-hidden className="pointer-events-none absolute inset-0 size-full" />
    </div>
  );
});

