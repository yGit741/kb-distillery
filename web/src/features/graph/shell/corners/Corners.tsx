import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDataSource } from "@/api";
import { useUi } from "@/app/ui-store";
import { useApiQuery } from "@/lib/useApiQuery";
import { IS_SHARE } from "@/share/env";
import { useTheme } from "@/theme/theme";
import { colorChannel, COLOR_TITLE } from "../../encoding/channels";
import type { ToolHost } from "../../hostContext";
import { layerGroups, type LayerGroup, type TypeRow } from "../../legendModel";
import { predicateFn } from "../../publicPredicate";
import type { GraphSchema } from "../../schema";
import { useGraphUi } from "../../store";
import { effectiveColorBy, METRIC_COLORS, RAMP_BY } from "../../style";
import type { GNode } from "../../types";
import { ago, defaultFetch, listRecent, listSessions, listViews, pinView, renameView, unpinView, type Fetcher, type SessionRow } from "./api";
import { ActionPill, CornerButton, MoreButton, PillAction, PushPin } from "./CornerButton";
import { ColourDots } from "./ColourDots";
import { useCorners, type Layer } from "./cornersStore";
import { Fan, type FanCard } from "./Fan";
import { BUTTON, EDGE, fanCapacity } from "./geometry";
import { PinList } from "./PinList";
import { useShellStore } from "../shellStore";
import { browserSessions, newChat, resumeSession } from "./sessions";
import { useShellTour } from "./shellTour";
import { ThinkIcon } from "./ThinkIcon";
import { TypesCard } from "./TypesCard";
import { applySpec, captureSpec, suggestName } from "./viewSpec";

export interface CornersProps {
  nodes: readonly GNode[];
  visible: ReadonlySet<string>;
  schema: GraphSchema;
  /** the types drawn (null = every type) */
  shownTypes: ReadonlySet<string> | null;
  /** the line "n of m pages ..." the old legend carried, kept for assistive tech */
  stats: string;
  host: ToolHost;
  /** the screen's own path for a named view */
  applyView: (id: string) => void;
  showPicked: (ids: string[]) => void;
  /** tests pass a mock; the app uses the browser's */
  fetchImpl?: Fetcher;
}

const LAYER_ORDER = ["concept", "collection", "source"] as const;
const isTyping = (t: EventTarget | null) => t instanceof HTMLElement && t.matches("input, textarea, select, [contenteditable=true]");
const BTN_ID = { pins: "corner-pins", think: "corner-think", agent: "corner-agent" } as const;
const MORE = 6; // gap between a corner button and its "..."

/**
 * The calm shell's corner controls and legends (flag `graph-shell`). Top-left: the pinned views. Top-right: Think
 * notes. Bottom-left: the agent's chats. Right edge: the colour legend. Bottom centre: the page types. Everything
 * floats over the graph with bare icons; each panel takes only the pointer events of its own controls.
 * Rules: the pinned list closes both fans and a fan closes the list; the two fans may be open together; Esc
 * closes the topmost layer; a click anywhere else closes all.
 */
export function Corners({ nodes, visible, schema, shownTypes, stats, host, applyView, showPicked, fetchImpl }: CornersProps) {
  const f = fetchImpl ?? defaultFetch;
  const ds = useDataSource();
  const qc = useQueryClient();
  const ui = useGraphUi();
  const theme = useTheme((s) => s.theme);
  const server = ds.kind === "http" && !IS_SHARE;
  const root = useRef<HTMLDivElement>(null);
  const order = useCorners((s) => s.order);
  const menu = useCorners((s) => s.menu);
  const activeView = useCorners((s) => s.activeView);
  const { toggle, openMenu, closeMenu, closeTop, closeAll, setActive } = useCorners.getState();
  const pinsOpen = order.includes("pins");
  const thinkOpen = order.includes("think");
  const agentOpen = order.includes("agent");

  // ---- the screen's height: how many cards a fan may show, where the legend can sit
  const [areaHeight, setAreaHeight] = useState(() => (typeof window === "undefined" ? 800 : Math.max(320, window.innerHeight - 48)));
  useEffect(() => {
    const el = root.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => el.clientHeight && setAreaHeight(el.clientHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const cap = fanCapacity(areaHeight);

  // ---- data
  const views = useQuery({ queryKey: ["corners", "views"], queryFn: () => listViews(f), enabled: server && pinsOpen, staleTime: 0 });
  const [recentOn, setRecentOn] = useState(false);
  const recent = useQuery({ queryKey: ["corners", "recent"], queryFn: () => listRecent(f), enabled: server && pinsOpen && recentOn, staleTime: 0 });
  const think = useApiQuery(["think"], (d) => d.listThink(), { enabled: server && thinkOpen });
  const sessions = useQuery({ queryKey: ["corners", "sessions"], queryFn: () => listSessions(f), enabled: server && agentOpen, staleTime: 0, retry: false });

  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(""), 4000);
    return () => clearTimeout(t);
  }, [notice]);
  const fail = (e: unknown) => setNotice(e instanceof Error ? e.message : String(e));
  const reload = () => void qc.invalidateQueries({ queryKey: ["corners", "views"] });

  // ---- pinned views
  const target = menu?.owner === "pins" ? (menu.id ?? activeView) : null;
  const targetView = views.data?.find((v) => v.id === target);
  const deps = useMemo(() => ({ applyView, showPicked }), [applyView, showPicked]);
  const pin = async (name: string) => {
    try {
      const res = await pinView(f, name, captureSpec(useGraphUi.getState()) as unknown as Record<string, unknown>);
      if (res.view) setActive(res.view.id);
      setNotice(`Pinned "${name}"`);
      reload();
    } catch (e) {
      fail(e);
    }
  };
  const rename = async (id: string, name: string) => {
    try {
      await renameView(f, id, name);
      reload();
    } catch (e) {
      fail(e);
    }
  };
  const unpin = async (id: string) => {
    const name = views.data?.find((v) => v.id === id)?.name ?? "view";
    closeMenu();
    try {
      await unpinView(f, id);
      if (useCorners.getState().activeView === id) setActive(null);
      setNotice(`Unpinned "${name}"`);
      reload();
    } catch (e) {
      fail(e);
    }
  };
  // a pinned view picked in the search panel opens the same way as one picked in the list
  const pendingView = useShellStore((s) => s.pendingView);
  useEffect(() => {
    if (!pendingView) return;
    useShellStore.getState().clearPendingView();
    setActive(pendingView.id);
    if (!applySpec(pendingView.spec, deps)) setNotice("Nothing in this view can be restored here");
  }, [pendingView, deps, setActive]);
  const recognised = useCallback((spec: Record<string, unknown>) => ["story", "types", "depths", "colorBy", "sizeBy", "hiddenKeys", "quick", "pages"].some((k) => k in spec), []);

  // ---- fans
  const thinkCards = useMemo<FanCard[]>(() => {
    const notes = [...(think.data?.notes ?? [])].sort((a, b) => b.mtime - a.mtime);
    const label = (n: string) => n.replace(/\.md$/, "");
    const cards = notes.map((n) => ({ key: n.name, title: label(n.name), meta: ago(new Date(n.mtime * 1000).toISOString()) }));
    return notes.length > cap ? [...cards.slice(0, cap - 1), { key: "__all", title: "All think notes", meta: String(notes.length) }] : cards;
  }, [think.data, cap]);
  const [serverChats, setServerChats] = useState(false);
  const chatRows = useMemo<SessionRow[]>(() => {
    if (sessions.data) return sessions.data;
    return agentOpen ? browserSessions() : [];
    // the browser's chat is read each time the fan opens
  }, [sessions.data, agentOpen]);
  useEffect(() => setServerChats(!!sessions.data), [sessions.data]);
  const agentCards = useMemo<FanCard[]>(() => {
    const cards = chatRows.map((r) => ({ key: r.id, title: r.title, meta: ago(r.updated), live: r.live }));
    return chatRows.length > cap ? [...cards.slice(0, cap - 1), { key: "__all", title: "All chats", meta: String(chatRows.length) }] : cards;
  }, [chatRows, cap]);

  const pickThink = (key: string) => {
    toggle("think");
    if (key === "__all") host.go("/think");
    else host.go("/think", { note: key });
  };
  const pickAgent = (key: string) => {
    toggle("agent");
    if (key === "__all") return host.go("/chat");
    const row = chatRows.find((r) => r.id === key);
    if (row) void resumeSession(f, row, serverChats).catch(fail);
  };

  // ---- Esc closes the topmost layer; a click outside closes them all
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (!useCorners.getState().order.length) return;
      if (isTyping(e.target) && !root.current?.contains(e.target as Node)) return;
      // a dialog (the palette, a confirm) owns Escape while it is open
      if (e.defaultPrevented || document.querySelector("[role=dialog]")) return;
      const closed = closeTop();
      if (!closed) return;
      // the screen's own Esc (clear the selection) must not also fire
      e.stopPropagation();
      e.preventDefault();
      if (closed === "pins" || closed === "think" || closed === "agent") document.getElementById(BTN_ID[closed])?.focus();
    };
    const onDown = (e: PointerEvent) => {
      if (!useCorners.getState().order.length) return;
      if (root.current && e.target instanceof Node && !root.current.contains(e.target)) closeAll();
    };
    window.addEventListener("keydown", onKey, { capture: true });
    document.addEventListener("pointerdown", onDown, { capture: true });
    return () => {
      window.removeEventListener("keydown", onKey, { capture: true });
      document.removeEventListener("pointerdown", onDown, { capture: true });
      useCorners.getState().closeAll();
      useCorners.getState().setActive(null);
    };
  }, [closeTop, closeAll]);

  // ---- the legends (what the old Legend showed, now in the right-edge dots and the bottom card)
  const by = effectiveColorBy(ui.colorBy);
  const ramp = RAMP_BY.has(by) ? theme : null;
  const keyPool = useMemo(() => {
    if (!ui.hiddenKeys.size) return visible;
    const keep = predicateFn(ui.predicate);
    const pool = new Set(visible);
    for (const n of nodes) if ((!shownTypes || shownTypes.has(n.type)) && (!keep || keep(n))) pool.add(n.id);
    return pool;
  }, [nodes, visible, shownTypes, ui.hiddenKeys, ui.predicate]);
  const key = useMemo(() => (by === "type" ? [] : colorChannel(by, { ramp }).rows(nodes.filter((n) => keyPool.has(n.id)))), [nodes, keyPool, by, ramp]);
  const groups = useMemo(() => layerGroups(nodes, visible, schema, shownTypes), [nodes, visible, schema, shownTypes]);
  const allTypes = useMemo(() => groups.flatMap((g) => g.rows.map((r) => r.id)), [groups]);
  const [concepts, sources] = useMemo((): [TypeRow[], TypeRow[]] => {
    const c = groups.find((g: LayerGroup) => g.layer === "concept")?.rows ?? [];
    const read = LAYER_ORDER.filter((l) => l !== "concept").flatMap((l) => groups.find((g) => g.layer === l)?.rows ?? []);
    return [c, read];
  }, [groups]);
  useShellTour(`${server}|${allTypes.length > 0}`);
  const spot = useCallback((types: readonly string[] | null) => useGraphUi.setState({ spotlight: types ? new Set(types) : null }), []);
  useEffect(() => () => useGraphUi.setState({ spotlight: null }), []);

  const placeMenu = (side: "left" | "right", corner: "top" | "bottom"): React.CSSProperties => ({
    position: "absolute",
    ...(side === "left" ? { left: EDGE + BUTTON + MORE + 28 + 6 } : { right: EDGE + BUTTON + MORE + 28 + 6 }),
    ...(corner === "top" ? { top: EDGE + (BUTTON - 28) / 2 } : { bottom: EDGE + (BUTTON - 28) / 2 }),
  });
  const moreAt = (side: "left" | "right", corner: "top" | "bottom"): React.CSSProperties => ({
    position: "absolute",
    ...(side === "left" ? { left: EDGE + BUTTON + MORE } : { right: EDGE + BUTTON + MORE }),
    ...(corner === "top" ? { top: EDGE + (BUTTON - 28) / 2 } : { bottom: EDGE + (BUTTON - 28) / 2 }),
  });
  const menuOpen = (o: Layer) => menu?.owner === o;

  return (
    <div ref={root} data-corners="root" data-testid="graph-corners" className="pointer-events-none absolute inset-0 z-20">
      <span className="sr-only" data-testid="graph-stats">
        {stats}
      </span>

      {server && (
        <>
          <PinList
            open={pinsOpen}
            views={views.data}
            viewsError={views.isError ? "error" : undefined}
            recent={recent.data}
            recentError={recent.isError ? "error" : undefined}
            suggest={suggestName(ui)}
            onApply={(spec, id) => {
              if (id) setActive(id);
              if (!applySpec(spec, deps)) setNotice("Nothing in this step can be restored here");
            }}
            onPin={(n) => void pin(n)}
            onRename={(id, n) => void rename(id, n)}
            onRecentOpen={setRecentOn}
            canApply={recognised}
          />
          <CornerButton id={BTN_ID.pins} label="Pinned views" data-tour="graph-views" on={pinsOpen} style={{ position: "absolute", left: EDGE, top: EDGE }} onClick={() => toggle("pins")}>
            <PushPin />
          </CornerButton>
          {pinsOpen && (
            <>
              <MoreButton label="Pinned view options" on={menuOpen("pins")} style={moreAt("left", "top")} onClick={() => (menu?.owner === "pins" ? closeMenu() : openMenu("pins"))} />
              {menuOpen("pins") && (
                <ActionPill label="Pinned view options" align="left" className="z-[30]" >
                  <PillAction
                    disabled={!targetView}
                    title={targetView ? `Rename "${targetView.name}"` : "Open a pinned view first"}
                    onClick={() => targetView && useCorners.getState().startEdit({ kind: "rename", id: targetView.id })}
                  >
                    Rename
                  </PillAction>
                  <PillAction disabled={!targetView} title={targetView ? `Unpin "${targetView.name}"` : "Open a pinned view first"} onClick={() => targetView && void unpin(targetView.id)}>
                    Unpin
                  </PillAction>
                </ActionPill>
              )}
            </>
          )}

          <CornerButton id={BTN_ID.think} label="Think notes" data-tour="graph-think" on={thinkOpen} style={{ position: "absolute", right: EDGE, top: EDGE }} onClick={() => toggle("think")}>
            <ThinkIcon />
          </CornerButton>
          <Fan kind="think" open={thinkOpen} label="Think notes" cards={thinkCards} empty={think.isLoading ? "Loading notes" : "No think notes yet"} onPick={pickThink} />
          {thinkOpen && (
            <>
              <MoreButton label="Think options" on={menuOpen("think")} style={moreAt("right", "top")} onClick={() => (menu?.owner === "think" ? closeMenu() : openMenu("think"))} />
              {menuOpen("think") && (
                <div style={placeMenu("right", "top")} className="z-[30] flex justify-end">
                  <ActionPill label="Think options" align="right">
                    <PillAction
                      onClick={() => {
                        useUi.getState().setCaptureOpen(true);
                        closeAll();
                      }}
                    >
                      New
                    </PillAction>
                    <PillAction
                      onClick={() => {
                        closeAll();
                        host.go("/think");
                      }}
                    >
                      Open full screen
                    </PillAction>
                  </ActionPill>
                </div>
              )}
            </>
          )}

          <CornerButton id={BTN_ID.agent} label="Agent chats" data-tour="graph-agent" on={agentOpen} style={{ position: "absolute", left: EDGE, bottom: EDGE }} onClick={() => toggle("agent")}>
            <Sparkles className="size-[22px]" strokeWidth={1.75} aria-hidden />
          </CornerButton>
          <Fan kind="agent" open={agentOpen} label="Agent chats" cards={agentCards} empty={sessions.isLoading ? "Loading chats" : "No chats yet"} onPick={pickAgent} />
          {agentOpen && (
            <>
              <MoreButton label="Agent options" on={menuOpen("agent")} style={moreAt("left", "bottom")} onClick={() => (menu?.owner === "agent" ? closeMenu() : openMenu("agent"))} />
              {menuOpen("agent") && (
                <div style={placeMenu("left", "bottom")} className="z-[30]">
                  <ActionPill label="Agent options" align="left">
                    <PillAction
                      onClick={() => {
                        closeAll();
                        newChat();
                      }}
                    >
                      New
                    </PillAction>
                    <PillAction
                      onClick={() => {
                        closeAll();
                        host.go("/chat");
                      }}
                    >
                      Open full screen
                    </PillAction>
                  </ActionPill>
                </div>
              )}
            </>
          )}
        </>
      )}

      {notice && (
        <div role="status" className="absolute left-1/2 -translate-x-1/2 rounded-full border bg-card px-3 py-1 text-xs shadow-[var(--shadow)]" style={{ top: EDGE + 56 }}>
          {notice}
        </div>
      )}

      <ColourDots
        rows={key}
        title={COLOR_TITLE[by].toLowerCase()}
        hidden={ui.hiddenKeys}
        toggleable={!METRIC_COLORS.has(by)}
        onToggle={(label) => ui.toggleKey(label)}
        areaHeight={areaHeight}
        thinkCards={Math.max(1, thinkCards.length)}
      />
      <TypesCard concepts={concepts} sources={sources} onToggle={(t) => ui.toggleType(t, allTypes, schema.defaultVisible)} onSpot={spot} />
    </div>
  );
}
