import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import { useKb } from "@/lib/store";
import { cn } from "@/lib/utils";
import { flag } from "@/flags";
import { useFlag } from "@/flags/useFlag";
import { useFavorites } from "./favorites/store";
import { useTheme } from "@/theme/theme";
import { readCanvasColors, withAlpha, type CanvasColors } from "./canvasTheme";
import { useLayers } from "./layers/store";
import { computeFocus, fadedLinkOpacity, fadedNodeOpacity, focusKey, nodeOpacity, type Focus } from "./focus";
import { ForceGraph, type Anchor, type ForceGraphHandle } from "./ForceGraph";
import { buildGraphData, edgeWeight, edgeWeights, largestComponent, sameSet, type NeighborMap } from "./graphData";
import { createHoverIntent, createSpeedMeter, HOVER_TUNING } from "./hoverIntent";
import { drawArcs } from "./lab/arcs";
import { drawHulls, drawLabelLayer, type FadeState } from "./lab/draw";
import { useLabHud } from "./lab/hud";
import { hopsFrom, type Importance } from "./lab/importance";
import { FORCED } from "./lab/labelPlan";
import { areaNames } from "./lab/regions";
import { drawKbOutlines, kbAnchors, kbGroups, kbLabelSpot } from "./lab/kbRegions";
import { bubbleAim, drawBubble, magnetCursor, pickMagnetic, rgbOf, stepBubble, type Bubble, type ScreenNode } from "./magnet";
import { useCites } from "./shell/citeStore";
import { candidatesOf } from "./shell/replay";
import { ReplayLegend } from "./shell/ReplayLegend";
import { useReplay } from "./shell/replayStore";
import { useSparkOpen } from "./shell/SparkPanelHost";
import { SPARK_PANEL_W } from "./shell/layout";
import { useFullChat } from "./shell/useFullChat";
import { drawPile, formatOfPile, isPile, isPileId, pileRadius } from "./rawLayer";
import { DRAG_PX } from "./selection";
import { useGraphUi } from "./store";
import { useDecor } from "./tools/decor";
import { drawNode as drawNodeMark } from "./encoding/canvas";
import { drawReplayMark, drawReplayPath } from "./shell/replayDraw";
import { personInitials, SOURCE_GLYPH_PX } from "./encoding/spec";
import { colorOf, effectiveColorBy, layeredRadii, METRIC_COLORS, nodeRadius, semanticRadius, type ColorBy, type SizeBy } from "./style";
import type { GNode, GraphModel, SimLink, SimNode } from "./types";

export interface CanvasHandle {
  screenOf: (id: string) => { x: number; y: number } | null;
  hovered: () => string | null;
  zoomBy: (factor: number) => void;
  reheat: () => void;
  /** a gentle, local spread of the nodes around a screen point (right-click menu "Spread here") */
  spreadAt: (clientX: number, clientY: number) => void;
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
  /** right-click on empty space, with where (client coordinates) */
  onBackgroundContext: (x: number, y: number) => void;
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
  /** zoom relative to "fit", from the last label frame: the semantic node size reads it */
  zr: number;
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

/**
 * The ring: every topic of the vault at a fixed angle (by id), at a radius sized once from the first drawn set.
 * Computed from the whole vault, not the drawn set, so a filter never re-spaces the map (ui-principles §29).
 */
export function themeRing(topicIds: readonly string[], drawnCount: number, linkDistance: number): Map<string, readonly [number, number]> {
  const ids = [...topicIds].sort((a, b) => a.localeCompare(b));
  const radius = (10 * Math.sqrt(drawnCount) + 60) * (linkDistance / 28);
  return new Map(
    ids.map((id, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, ids.length);
      return [id, [radius * Math.cos(a), radius * Math.sin(a)] as const];
    }),
  );
}

/** Topics pinned on the ring; their pages are pulled toward it (the anchored, map-like layout). */
function themeAnchors(nodes: readonly SimNode[], ring: ReadonlyMap<string, readonly [number, number]>): Map<string, readonly [number, number]> {
  const out = new Map<string, readonly [number, number]>();
  for (const t of [...nodes].filter((n) => n.type === "topic").sort((a, b) => a.id.localeCompare(b.id))) {
    const p = ring.get(t.id);
    if (!p) continue;
    t.fx = p[0];
    t.fy = p[1];
    if (t.areas[0] && !out.has(t.areas[0])) out.set(t.areas[0], p);
  }
  return out;
}

const endId = (e: string | SimNode) => (typeof e === "string" ? e : e.id);

/** Flag calm-graph: edges rest at this share of the usual opacity (a hovered page still lights its own). */
const CALM_EDGE = 0.4;
const DOUBLE_MS = 380;

/**
 * The graph itself: force-graph plus the mouse scheme. Modeless: hover always labels a node and a click
 * labels its neighbours; the wheel pans, pinch or Cmd+wheel zooms; double-click opens the side reader;
 * right-click a node opens its menu. Box, lasso and path selection are tools (./tools), not here.
 */
const NO_NAMES: ReadonlyMap<string, string> = new Map();

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
    zr: 1,
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
  // flag calm-graph: reacts to the flag arriving late; hover always settles first and edges rest fainter
  const calmOn = useFlag("calm-graph");
  const calmRef = useRef(calmOn);
  calmRef.current = calmOn;
  // pages the answer in the left chat panel cites (./shell/citeStore): lit while it is on screen, never selected
  const citeSlugs = useCites((s) => s.slugs);
  const citeFitTick = useCites((s) => s.fitTick);
  const sparkOpen = useSparkOpen();
  // the full chat gives the canvas its own box (the right pane): frame inside it, with room for the labels
  const { full: fullChat } = useFullChat();
  const sparkChat = useFlag("spark-chat");
  // a replay of how an answer was built (./shell/replayStore) lights its trail through the same focus: the camera stays
  const replayView = useReplay((s) => (sparkChat ? s.view : null));
  const replayCandidates = useReplay((s) => s.candidates);
  const replayMissed = useReplay((s) => s.missed);
  const replayBad = useReplay((s) => s.bad);
  const candidates = useMemo(
    () => (replayView?.atEnd ? candidatesOf([...replayView.roles].filter(([, r]) => r === "read").map(([id]) => id), neighbors, new Set(replayView.roles.keys()), visible) : []),
    [replayView, neighbors, visible],
  );
  useEffect(() => {
    useReplay.getState().setCandidates(candidates);
  }, [candidates]);
  const replay = useMemo(
    () => (replayView ? { view: replayView, candidates: new Set(replayView.atEnd ? replayCandidates : []), missed: new Set(replayMissed), bad: new Set(replayBad) } : null),
    [replayView, replayCandidates, replayMissed, replayBad],
  );
  const cited = useMemo<ReadonlySet<string>>(() => {
    if (!sparkChat) return new Set();
    if (replay) return new Set([...replay.view.roles.keys(), ...replay.candidates, ...replay.missed, ...replay.bad].filter((id) => visible.has(id)));
    return new Set(citeSlugs.filter((id) => visible.has(id)));
  }, [sparkChat, citeSlugs, visible, replay]);
  const fitSeen = useRef(citeFitTick); // the tick a remounted canvas starts at is not a request
  // a `>` sentence waiting for its second Enter (flag graph-intent): the pages it would keep light up, the rest dims
  const previewIds = useLayers((st) => st.preview?.ids ?? null);
  const live = useRef({ ui, theme, selection, byId, neighbors, visible, cited, previewIds, replay, onOpenReader, onOpenMenu, onBackgroundContext, onOpenPile });
  live.current = { ui, theme, selection, byId, neighbors, visible, cited, previewIds, replay, onOpenReader, onOpenMenu, onBackgroundContext, onOpenPile };

  rs.current.imp = imp;
  const names = useMemo(() => areaNames(model.nodes, model.kbs), [model]);
  const initials = useMemo(() => personInitials(model.nodes), [model]);
  const weights = useMemo(() => edgeWeights(model), [model]);
  const weightsRef = useRef(weights);
  weightsRef.current = weights;
  // the drawn set, swapped only when its members change: `visible` is a new Set on every selection change (the
  // quick filters read the selection), and the force data built from it restarts the layout (a click used to move
  // the graph). Everything keyed on the drawn set uses `shown`.
  const drawn = useRef(visible);
  if (!sameSet(drawn.current, visible)) drawn.current = visible;
  const shown = drawn.current;
  const core = useMemo(() => largestComponent(shown, neighbors), [shown, neighbors]);
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
  // each layer sized on its own scale (./style layeredRadii), over the pages drawn
  const layered = useMemo(() => layeredRadii(model.nodes.filter((n) => shown.has(n.id)), radiusOpts), [model, shown, radiusOpts]);
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
    const { ui: u, selection: sel, byId: ids, neighbors: nb, visible: vis, cited: cite, previewIds: pre } = live.current;
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
    const base = hops ? { core: new Set(sel), lit: new Set(hops.keys()) } : computeFocus(sel, hover, nb, u.highlight);
    const preIds = pre ? new Set([...pre].filter((id) => vis.has(id))) : null;
    const next: Focus | null = preIds
      ? { core: preIds, lit: preIds, dim: 0.15 }
      : spotIds
      ? { core: spotIds, lit: spotIds, dim: 0.15 }
      : cite.size
        ? {
            // the cited pages stay lit and the rest stays dim across a click or hover: the user's own focus joins them
            core: new Set([...cite, ...(base?.core ?? []), ...(hover ? [hover] : [])]),
            lit: new Set([...cite, ...(base?.lit ?? []), ...(hover ? [hover] : [])]),
            dim: base?.dim ?? 0.3,
          }
        : base;
    startFade(rs.current.focus, next, u.calmHover || calmRef.current);
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
    for (const id of cite) put(id, FORCED.type);
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
    enabled: () => live.current.ui.calmHover || calmRef.current,
  });
  const pointed = useCallback(() => intent.current?.pointed() ?? null, []);
  const setHover = useCallback((id: string | null) => {
    if (intent.current?.pointed() === id) return;
    wrap.current?.classList.toggle("graph-pointer", id !== null);
    intent.current?.request(id);
    fg.current?.refresh(); // the ring follows the pointer at once
  }, []);
  useEffect(() => {
    if (!ui.calmHover && !calmOn) intent.current?.flush();
  }, [ui.calmHover, calmOn]);
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
    return buildGraphData(model, shown, prev);
  }, [model, shown]);

  // the anchored layout pins topics on a ring and pulls every page toward its theme; free unpins them
  // the ring is sized once per vault and link distance (from the first drawn set), then stays where it is
  const ringRef = useRef<{ model: GraphModel; linkDistance: number; ring: Map<string, readonly [number, number]> } | null>(null);
  const anchors = useMemo(() => {
    const nodes = data.nodes as SimNode[];
    if (ui.layoutMode !== "anchored") {
      for (const n of nodes) if (n.type === "topic") n.fx = n.fy = undefined;
      return null;
    }
    const r = ringRef.current;
    if (!r || r.model !== model || r.linkDistance !== ui.linkDistance) {
      const topics = model.nodes.filter((n) => n.type === "topic").map((n) => n.id);
      ringRef.current = { model, linkDistance: ui.linkDistance, ring: themeRing(topics, nodes.length, ui.linkDistance) };
    }
    return themeAnchors(nodes, ringRef.current!.ring);
  }, [data, model, ui.layoutMode, ui.linkDistance]);
  // several knowledge bases: each is pulled toward its own anchor (a row, left to right), so its pages stay one
  // region and a page with no links cannot drift off; dragging a region's name moves its anchor
  const kbIds = useMemo(() => ((model.kbs?.length ?? 0) > 1 ? model.kbs!.map((k) => k.id) : []), [model]);
  const kbAnchor = useRef(new Map<string, [number, number]>());
  useMemo(() => {
    const counts = new Map<string, number>();
    for (const n of model.nodes) if (n.kb) counts.set(n.kb, (counts.get(n.kb) ?? 0) + 1);
    kbAnchor.current = kbAnchors(kbIds, counts, ui.linkDistance);
  }, [kbIds, model, ui.linkDistance]);
  const anchor = useMemo<Anchor | null>(
    () =>
      kbIds.length
        ? { strength: 0.12, target: (n) => (n.kb ? (kbAnchor.current.get(n.kb) ?? null) : null) }
        : anchors
        ? {
            strength: ui.areaPull,
            target: (n) => {
              const a = n.type === "topic" ? undefined : anchors.get(n.areas?.[0] ?? "");
              return a ? [a[0] * 0.75, a[1] * 0.75] : null;
            },
          }
        : null,
    [anchors, ui.areaPull, kbIds],
  );
  // the first layout already uses the mode and pull (settled off screen); only the user's later change animates
  // (compared by value, so StrictMode's second mount run doesn't count as a change)
  const layoutWas = useRef<string | null>(null);
  useEffect(() => {
    const now = `${ui.layoutMode}|${ui.areaPull}`;
    if (layoutWas.current !== null && layoutWas.current !== now) fg.current?.reheat();
    layoutWas.current = now;
  }, [ui.layoutMode, ui.areaPull]);

  useEffect(() => {
    fg.current?.refresh();
  }, [ui.hiddenLinkKinds]);

  // ---- tool decor (experiment halos, faded links) is read at draw time; a change only needs a redraw
  useEffect(() => useDecor.subscribe(() => fg.current?.refresh()), []);
  // a favorite page wears a quiet ring (flag graph-intent)
  useEffect(() => useFavorites.subscribe(() => fg.current?.refresh()), []);

  // ---- redraw when anything the draw reads changes
  useEffect(() => {
    rs.current.colors = readCanvasColors();
    recompute();
  }, [recompute, theme, visible, selection, byId, neighbors, ui.highlight, ui.lab, ui.typeLabels, ui.spotlight, ui.colorBy, ui.linkOpacity, radiusOpts, layered, imp, cited, previewIds, calmOn]);

  // a changed set of pages is framed after a moment and framed again once the layout settles: at the moment the
  // pages may still be drifting from their old places, and a single early fit left a view (Thesis) in a corner.
  // Panning or zooming in between cancels the settled fit, so it never takes the view away from the user.
  useEffect(() => {
    pendingFit.current = true;
    const t = window.setTimeout(() => {
      if (pendingFit.current) fitRef.current();
    }, 1600);
    return () => window.clearTimeout(t);
  }, [ui.shownTypes, ui.shownDepths, ui.view]);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const mine = () => (pendingFit.current = false);
    el.addEventListener("wheel", mine, { passive: true });
    el.addEventListener("pointerdown", mine);
    return () => {
      el.removeEventListener("wheel", mine);
      el.removeEventListener("pointerdown", mine);
    };
  }, []);

  // ---- fit (largest connected component: stray islands drift far out and would shrink everything)
  const multiKb = useRef(false);
  multiKb.current = (model.kbs?.length ?? 0) > 1;
  const mounted = useRef(true);
  useEffect(() => () => void (mounted.current = false), []);
  const framed = useRef(false);
  const fit = useCallback((ms = 400) => {
    // a canvas with no size yet (still laying out) would frame everything into its corner: try again shortly,
    // but never after unmount (a canvas that never gets a size, as in jsdom, would retry forever)
    if (!wrap.current?.clientWidth || !wrap.current.clientHeight) {
      window.setTimeout(() => mounted.current && fitRef.current(ms), 200);
      return;
    }
    if (!live.current.visible.size) return;
    // several knowledge bases are separate islands by design: frame them all, not the largest one
    const core = multiKb.current ? new Set<string>() : largestComponent(live.current.visible, live.current.neighbors);
    fg.current?.fit(core.size > 1 ? (n) => core.has(n.id) || isPile(n) : undefined, ms);
    framed.current = true;
    window.setTimeout(() => {
      k.current = fg.current?.zoom() ?? 1;
      recompute();
    }, ms + 50);
  }, [recompute]);

  const fitRef = useRef(fit);
  fitRef.current = fit;
  useEffect(() => {
    if (ui.fitTick > 0) fit();
  }, [ui.fitTick, fit]);

  // a new answer (or a chat opened) frames the cited pages in the area right of the chat panel; nothing else re-frames
  useEffect(() => {
    if (citeFitTick === fitSeen.current) return;
    fitSeen.current = citeFitTick;
    let tries = 0;
    let timer = 0;
    const attempt = () => {
      const ids = live.current.cited;
      if (!ids.size) return;
      pendingFit.current = false;
      if (fg.current?.fitIn((n) => ids.has(n.id), sparkOpen && !fullChat ? SPARK_PANEL_W : 0, 600, fullChat ? 110 : 72)) {
        window.setTimeout(() => {
          k.current = fg.current?.zoom() ?? 1;
          recompute();
        }, 650);
      } else if (tries++ < 40) timer = window.setTimeout(attempt, 100);
    };
    attempt();
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [citeFitTick]);

  // ---- pending focus: wait for the page to be drawn and laid out, then centre on it
  useEffect(() => {
    const req = ui.focusRequest;
    if (!req) return;
    const node = byId.get(req.id);
    if (!node) {
      useGraphUi.setState({ focusRequest: null });
      return;
    }
    if (!shown.has(req.id)) {
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
  }, [ui.focusRequest, byId, shown, data]);

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
      else if (!node) live.current.onBackgroundContext(x, y);
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
      spreadAt: (x, y) => fg.current?.spreadAt(x, y),
    }),
    [],
  );
  // read-only probe for the e2e motion tests (tests/e2e): every drawn page's id and screen position
  useEffect(() => {
    const w = window as unknown as { __kbGraph?: unknown };
    w.__kbGraph = {
      selected: () => live.current.selection.size,
      nodes: () =>
        (fg.current?.nodes() ?? []).map((n) => ({ id: n.id, type: n.type, deg: live.current.neighbors.get(n.id)?.length ?? 0, gx: n.x, gy: n.y, ...(fg.current?.screenOf(n) ?? { x: NaN, y: NaN }) })),
    };
    return () => void delete w.__kbGraph;
  }, []);

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
      const rp = live.current.replay;
      if (rp?.view.atEnd && rp.candidates.has(id)) {
        useReplay.getState().toggleMissed(id); // a page the agent could have read: marked, not selected
        return;
      }
      if (rp) useReplay.getState().pick(rp.view.roles.get(id) === "cited" ? id : null);
      if (!rp && live.current.cited.has(id)) useCites.getState().scrollTo(id);
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
      // a spotlit type (legend hover) is drawn a third larger as well as lit; semantic zoom (./style)
      const r0 = radius(n) * (live.current.ui.spotlight?.has(n.type) ? 1.3 : 1);
      const r = semanticRadius(r0, scale, rs.current.zr);
      const alpha = fadedNodeOpacity(n.id, focus, rs.current.prevFocus, rs.current.fadeT);
      const isSel = selected.has(n.id);
      const halo = useDecor.getState().halo?.get(n.id);
      if (halo) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + (2 + 4 * halo) / scale, 0, 2 * Math.PI);
        ctx.fillStyle = withAlpha(colors.warn, 0.15 + 0.55 * halo);
        ctx.fill();
      }
      const by = effectiveColorBy(live.current.ui.colorBy);
      // an ordered colouring is a neutral ramp (lightness), so it never fights the area hulls
      const col = colorOf(n, by, METRIC_COLORS.has(by) ? metricOf(rs.current.imp, n, by) : undefined, live.current.theme);
      // the shared encoding (./encoding): selection ring or hover glow, then the type's mark; a source is a plain dot
      // until it is big enough on screen (zoom) or under the pointer, then its type glyph
      drawNodeMark(ctx, n.type, {
        x: n.x,
        y: n.y,
        r,
        color: col,
        background: colors.background,
        font: colors.font,
        ring: colors.ring,
        initials: initials.get(n.id),
        state: isSel ? "selected" : hover === n.id ? "hover" : !live.current.replay && live.current.cited.has(n.id) ? "focus" : flag("graph-intent") && useFavorites.getState().slugs.has(n.id) ? "favorite" : null,
        alpha,
        glyph: r * scale >= SOURCE_GLYPH_PX || hover === n.id,
        scale,
      });
      if (live.current.replay) drawReplayMark(ctx, n.id, n.x, n.y, r, scale, alpha, live.current.replay, colors);
    },
    [radius, initials],
  );

  // ---- knowledge base names: DOM labels above each region (clear of the top nodes' own labels), placed every
  // frame, draggable (moves the region)
  const kbLabels = useRef(new Map<string, HTMLButtonElement>());
  const placeKbLabels = () => {
    const g = fg.current;
    const el = wrap.current;
    if (!g || !el || !kbLabels.current.size) return;
    const box = el.getBoundingClientRect();
    const groups = kbGroups(g.nodes().filter((n) => !isPile(n)));
    for (const [id, label] of kbLabels.current) {
      const list = groups.get(id);
      const spot = list?.length ? kbLabelSpot(list) : null;
      const p = spot ? g.screenOf({ x: spot.x, y: spot.top }) : null;
      if (!p) {
        label.style.visibility = "hidden";
        continue;
      }
      label.style.visibility = "visible";
      label.style.transform = `translate(${p.x - box.left}px, ${p.y - box.top}px) translate(-50%, calc(-100% - 34px))`;
    }
  };
  const kbDrag = useRef<{ id: string; x: number; y: number; nodes: SimNode[] } | null>(null);
  const startKbDrag = (id: string, e: React.PointerEvent) => {
    const g = fg.current;
    if (!g || e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const nodes = kbGroups(g.nodes()).get(id) ?? [];
    for (const n of nodes) [n.fx, n.fy] = [n.x, n.y];
    kbDrag.current = { id, x: e.clientX, y: e.clientY, nodes };
  };
  const moveKbDrag = (e: React.PointerEvent) => {
    const d = kbDrag.current;
    const g = fg.current;
    if (!d || !g) return;
    const k = g.zoom() || 1;
    const dx = (e.clientX - d.x) / k;
    const dy = (e.clientY - d.y) / k;
    d.x = e.clientX;
    d.y = e.clientY;
    for (const n of d.nodes) {
      n.x = n.fx = (n.x as number) + dx;
      n.y = n.fy = (n.y as number) + dy;
    }
    const a = kbAnchor.current.get(d.id);
    if (a) kbAnchor.current.set(d.id, [a[0] + dx, a[1] + dy]);
    g.refresh();
  };
  const endKbDrag = () => {
    const d = kbDrag.current;
    if (!d) return;
    for (const n of d.nodes) n.fx = n.fy = undefined;   // the moved anchor holds the region where it was dropped
    kbDrag.current = null;
  };

  const drawFramePre = useCallback(
    (ctx: CanvasRenderingContext2D, scale: number) => {
      const g = fg.current;
      if (!g) return;
      const arcs = useDecor.getState().arcs;
      const rp = live.current.replay;
      if (rp?.view.path.length) drawReplayPath(ctx, g.nodes(), rp.view.path, scale, rs.current.colors);
      if (arcs?.length) drawArcs(ctx, g.nodes(), arcs, scale, rs.current.colors);
      const u = live.current.ui;
      // hulls say where (area tints, or one per knowledge base when several share the canvas) and show only
      // when the nodes do not already say it with their colour
      if (kbIds.length) {
        drawKbOutlines(ctx, kbGroups(g.nodes().filter((n) => !isPile(n))), scale, rs.current.colors.muted);
        return;
      }
      const hulls = effectiveColorBy(u.colorBy) !== "area";
      if (hulls) drawHulls(ctx, g.nodes().filter((n) => !isPile(n)), scale, names, u.lab.hullSigma);
    },
    [names, kbIds],
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
        areaNames: kbIds.length ? NO_NAMES : names,   // knowledge base names are the DOM labels below
        fades: fades.current,
        pointer: cfg.lens ? pointer : null,
        hovered: hover,
        dt,
        strip: typesStripRect(el),
        nodeColor: (n) => {
          const u = live.current.ui;
          const by = effectiveColorBy(u.colorBy);
          return colorOf(n, by, METRIC_COLORS.has(by) ? metricOf(rs.current.imp, n, by) : undefined, live.current.theme);
        },
      });
      placeKbLabels();
      f.churn = f.churn * 0.9 + res.changes * (1000 / Math.max(16, dt)) * 0.1;
      rs.current.zr = res.zr;
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
    [radius, names, kbIds],
  );

  const drawLinkAfter = useCallback((l: SimLink, ctx: CanvasRenderingContext2D, scale: number) => {
    if (l.kind !== "shared" || scale < 1.6 || live.current.ui.hiddenLinkKinds.has(l.kind)) return;
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
    // a hidden kind keeps its place in the layout and is simply not drawn
    if (live.current.ui.hiddenLinkKinds.has(l.kind)) return withAlpha(colors.link, 0);
    return withAlpha(colors.link, fade * fadedLinkOpacity(a, b, focus, prevFocus, fadeT, live.current.ui.linkOpacity * (calmOn ? CALM_EDGE : 1), l.kind));
  }, [calmOn]);
  const linkWidth = useCallback((l: SimLink) => (l.kind === "shared" ? 0.35 + Math.min(l.shared ?? 1, 6) * 0.1 : 0.8), []);
  const linkLabel = useCallback(
    (l: SimLink) => (l.kind === "shared" && !live.current.ui.hiddenLinkKinds.has(l.kind) ? `${l.shared} shared source${l.shared === 1 ? "" : "s"}` : ""),
    [],
  );

  const onZoom = useCallback((z: number) => {
    k.current = z;
  }, []);

  const onEngineStop = useCallback(() => {
    if (!pendingFit.current) return;
    pendingFit.current = false;
    // the first frame is framed at once: a zoom animation on load is motion that explains nothing
    fit(framed.current ? 400 : 0);
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
      {replay && <ReplayLegend atEnd={replay.view.atEnd} />}
      {kbIds.map((id) => (
        <button
          key={id}
          type="button"
          ref={(el) => void (el ? kbLabels.current.set(id, el) : kbLabels.current.delete(id))}
          data-kb-region={id}
          title="Drag to move this knowledge base"
          className="absolute left-0 top-0 cursor-grab touch-none select-none whitespace-nowrap rounded px-1 text-sm font-bold uppercase tracking-wide text-muted-foreground hover:text-foreground active:cursor-grabbing"
          style={{ visibility: "hidden" }}
          onPointerDown={(e) => startKbDrag(id, e)}
          onPointerMove={moveKbDrag}
          onPointerUp={endKbDrag}
          onPointerCancel={endKbDrag}
        >
          {model.kbs?.find((k) => k.id === id)?.name ?? id}
        </button>
      ))}
    </div>
  );
});


/** The page-type strip's box in the canvas's CSS px, with air around it; null when the strip is not rendered. */
function typesStripRect(canvas: HTMLElement): [number, number, number, number] | null {
  const strip = canvas.ownerDocument.querySelector('[data-corners="types"]');
  if (!strip) return null;
  const s = strip.getBoundingClientRect();
  const c = canvas.getBoundingClientRect();
  if (s.width === 0 || s.height === 0) return null;
  return [s.left - c.left - 14, s.top - c.top - 8, s.right - c.left + 14, s.bottom - c.top + 8];
}
