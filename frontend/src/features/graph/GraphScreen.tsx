import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useDataSource } from "@/api";
import { HEADER_SLOT_ID } from "@/app/headerSlot";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { IS_SHARE } from "@/share/env";
import { useKb } from "@/lib/store";
import { useApiQuery } from "@/lib/useApiQuery";
import type { GraphSearch } from "@/routes/search";
import { Finder, FINDER_ID } from "./Finder";
import { HostContext, type ToolHost } from "./hostContext";
import { useLayer } from "./layerStore";
import "./tools/register";
import { askAbout, useChatDock } from "./tools/chatDockStore";
import "./kalai/register";
import { extendView, makeView, parsePages, scopeIds, type GraphView } from "./pageSearch";
import { buildNeighborMap } from "./graphData";
import { GraphCanvas, type CanvasHandle } from "./GraphCanvas";
import { Inspector } from "./Inspector";
import { computeImportance } from "./lab/importance";
import { HoverCard } from "./lab/HoverCard";
import { LabRail } from "./lab/LabRail";
import { initialView } from "./defaultView";
import { storyById } from "./lab/views";
import { Legend } from "./Legend";
import { predicateFn } from "./publicPredicate";
import { ViewsBar } from "./views/ViewsBar";
import { NodeMenu } from "./NodeMenu";
import { applyQuick } from "./quickFilters";
import { computeVisible } from "./rules";
import { assignAreaColors, colorKey, effectiveColorBy } from "./style";
import { parseSchema } from "./schema";
import { SideReader } from "./SideReader";
import { useGraphUi } from "./store";
import { Toolbar } from "./Toolbar";
import { KbPicker, parseKbs } from "./KbPicker";
import { useFlag } from "@/flags/useFlag";
import { TOOLS, useVisibleTools, type GraphToolContext } from "./tools";
import { flagOn, useExperiments } from "./tools/experiments";
import { toModel, type GNode } from "./types";
import { LAYER_TYPES, type Layer } from "@/api/model";
import "./tours";

/** How the screen reaches the rest of the app (the router lives in index.tsx; tests pass plain functions). */
export interface GraphHost extends ToolHost {
  pageHref: (slug: string, kb?: string) => string;
  /** Drop URL params once the view they describe is cleared. */
  clearParams: (keys: string[]) => void;
  /** Merge params into the URL (undefined or "" removes one); a view pill writes `view` so the link carries it. */
  setParams: (patch: Record<string, string | undefined>) => void;
}

const LIVE_MS = 10_000;
/** The data layer carries the whole corpus: poll it slowly. */
const LIVE_RAW_MS = 30_000;

export function GraphScreen({ search, host }: { search: GraphSearch; host: GraphHost }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const live = useGraphUi((s) => s.liveSync);
  const kbViewOn = useFlag("kb-view") && ds.kind !== "embedded";
  const kbs = useMemo(() => (kbViewOn ? parseKbs(search.kbs) : []), [kbViewOn, search.kbs]);
  // the data layer is the server's own knowledge base's: it is off while other knowledge bases are shown
  const rawOn = useLayer((s) => s.rawOn) && ds.kind !== "embedded" && !kbs.length;
  const q = useApiQuery(["graph", rawOn, kbs.join(",")], (d) => d.getGraph({ ...(rawOn ? { raw: true } : {}), ...(kbs.length ? { kbs } : {}) }), {
    refetchInterval: live ? (rawOn ? LIVE_RAW_MS : LIVE_MS) : false,
    // switching the data layer on or off keeps the canvas (and its positions) until the new snapshot lands
    placeholderData: keepPreviousData,
  });
  const snap = q.data;

  // The model is rebuilt only when the wiki changed (etag), not on every poll.
  const etag = snap?.etag;
  const model = useMemo(() => (snap ? toModel(snap) : null), [etag, snap?.layer]); // eslint-disable-line react-hooks/exhaustive-deps
  const schema = useMemo(() => parseSchema(snap?.schema), [etag]); // eslint-disable-line react-hooks/exhaustive-deps
  // a node of another knowledge base opens its page read-only (`?kb=`); ids may be `<kb>:<slug>`
  const kbHost = useMemo<GraphHost>(() => {
    if (!model) return host;
    const own = new Set((snap?.kbs ?? []).filter((k) => k.active).map((k) => k.id));
    const nodes = new Map(model.nodes.map((n) => [n.id, n]));
    const ref = (id: string): [string, string | undefined] => {
      const n = nodes.get(id);
      return n ? [n.slug ?? n.id, n.kb && !own.has(n.kb) ? n.kb : undefined] : [id, undefined];
    };
    return {
      ...host,
      openPage: (id) => {
        const [slug, kb] = ref(id);
        if (kb) host.openPage(slug, kb);
        else host.openPage(slug);
      },
      pageHref: (id) => {
        const [slug, kb] = ref(id);
        return kb ? host.pageHref(slug, kb) : host.pageHref(slug);
      },
      foreignKb: (id) => ref(id)[1],
    };
  }, [host, model, snap?.kbs]);
  // picking knowledge bases shows each one's default types, even over a type filter saved for the server's own
  const kbsKey = kbs.join(",");
  useEffect(() => {
    if (!kbsKey || !etag) return;
    const shown = useGraphUi.getState().shownTypes;
    if (shown && schema.defaultVisible.some((t) => !shown.has(t)))
      useGraphUi.setState({ shownTypes: new Set([...shown, ...schema.defaultVisible]) });
  }, [kbsKey, etag]); // eslint-disable-line react-hooks/exhaustive-deps
  const picker = kbViewOn ? <KbPicker selected={kbs} onChange={(ids) => host.setParams({ kbs: ids.join(",") || undefined })} /> : null;

  if (q.isLoading) return <FullBleed><div className="p-4"><Loading label="Loading graph" rows={4} /></div></FullBleed>;
  if (q.isError || !snap || !model)
    return (
      <FullBleed>
        {picker}
        <div className="p-4">
          <ErrorState title="Could not load the graph." error={q.error} onRetry={() => void q.refetch()} />
        </div>
      </FullBleed>
    );
  if (!model.nodes.length)
    return (
      <FullBleed>
        {picker}
        <div className="p-4"><Empty>The vault has no pages yet.</Empty></div>
      </FullBleed>
    );
  return (
    <FullBleed>
      {picker}
      <Loaded
        model={model}
        schema={schema}
        host={kbHost}
        search={search}
        generatedAt={snap.generated_at}
        refreshing={q.isFetching}
        onRefresh={() => void qc.invalidateQueries({ queryKey: ["graph"] })}
        dsKind={ds.kind}
      />
    </FullBleed>
  );
}

/** The screen sits under the 48px header and fills the rest of the viewport (the graph needs the room). */
function FullBleed({ children }: { children: React.ReactNode }) {
  return (
    <div className={"fixed inset-x-0 bottom-0 top-12 z-30 overflow-hidden bg-background"} data-testid="graph-screen">
      {children}
    </div>
  );
}

/** The rail sits beside the graph on a desktop and over it on a phone. */
function useWide(): boolean {
  const [wide, setWide] = useState(() => typeof window === "undefined" || window.innerWidth >= 640);
  useEffect(() => {
    const on = () => setWide(window.innerWidth >= 640);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return wide;
}

const isTyping = (t: EventTarget | null) => t instanceof HTMLElement && t.matches("input, textarea, select, [contenteditable=true]");

function Loaded({
  model,
  schema,
  host,
  search,
  generatedAt,
  refreshing,
  onRefresh,
  dsKind,
}: {
  model: ReturnType<typeof toModel>;
  schema: ReturnType<typeof parseSchema>;
  host: GraphHost;
  search: GraphSearch;
  generatedAt: string;
  refreshing: boolean;
  onRefresh: () => void;
  dsKind: string;
}) {
  const visibleTools = useVisibleTools();
  const ds = useDataSource();
  const ui = useGraphUi();
  const selection = useKb((s) => s.selection);
  const canvas = useRef<CanvasHandle>(null);
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  /** the right-click menu on empty space: spread the nodes around the point, or fit the view */
  const [bgMenu, setBgMenu] = useState<{ x: number; y: number } | null>(null);
  const [note, setNote] = useState("");

  // area colours by size, before anything below colours a node, a hull or a key row
  useMemo(() => assignAreaColors(model.nodes), [model]);
  const byId = useMemo(() => new Map(model.nodes.map((n) => [n.id, n] as const)), [model]);
  const neighbors = useMemo(() => buildNeighborMap(model.links), [model]);
  const shownTypes = useMemo(
    () => (ui.shownTypes === undefined ? new Set(schema.defaultVisible) : ui.shownTypes),
    [ui.shownTypes, schema],
  );
  const filtered = useMemo(
    () =>
      computeVisible(model.nodes, {
        shownTypes,
        shownDepths: ui.shownDepths,
        search: ui.search,
        rules: ui.rules,
        restrict: ui.view?.shown ?? null,
        force: !!ui.view,
        revealed: ui.revealed,
        keep: predicateFn(ui.predicate),
        hiddenKeys: ui.hiddenKeys,
        keyOf: (n) => colorKey(n, effectiveColorBy(ui.colorBy)),
      }),
    [model, shownTypes, ui.shownDepths, ui.search, ui.rules, ui.view, ui.revealed, ui.predicate, ui.hiddenKeys, ui.colorBy],
  );
  // the legend's one-click filters run last, on what the others left (./quickFilters)
  const visible = useMemo(() => applyQuick(filtered, byId, neighbors, selection, ui.quick), [filtered, byId, neighbors, selection, ui.quick]);
  const imp = useMemo(() => computeImportance({ visible, byId, neighbors, cfg: ui.lab }), [visible, byId, neighbors, ui.lab]);
  const wide = useWide();
  const stats = `${visible.size} of ${model.nodes.length} pages · ${model.links.length} links · ${generatedAt.slice(0, 16).replace("T", " ")}${dsKind === "embedded" ? " · snapshot" : ""}`;

  // ---- views (search, picked pages, scope)
  const setView = useCallback(
    (view: GraphView | null, emptyNote = "") => {
      useGraphUi.setState({ view });
      setNote(view ? "" : emptyNote);
      if (view) useKb.getState().setSelection(view.hits);
    },
    [],
  );
  const showPicked = useCallback(
    (ids: string[], exact = false) => {
      const next = makeView("picked", "picked", ids, byId, neighbors);
      // a Home subgraph is shown as drawn: exactly its pages (no extra hop), replacing any earlier pick
      if (exact && next) setView({ ...next, shown: new Set(next.hits) }, "No such pages in the graph.");
      else setView(extendView(useGraphUi.getState().view, next), "No such pages in the graph.");
    },
    [byId, neighbors, setView],
  );
  const showMentions = useCallback(
    async (query: string) => {
      try {
        const res = await ds.search(query, 2000);
        setView(makeView("search", query, res.hits.map((h) => h.id), byId, neighbors), `No pages mention “${query}”.`);
      } catch (e) {
        setNote(`Search failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
    [ds, byId, neighbors, setView],
  );
  const clearView = useCallback(() => {
    useGraphUi.setState({ view: null });
    setNote("");
    useKb.getState().clearSelection();
    host.clearParams(["search", "pages", "scope"]);
  }, [host]);

  // ---- headline views: a story, plus its seed view (Thesis) or tool panel (Explore); the URL carries `view`
  /** the view id this screen applied last: the URL echo of a pill click must not apply it a second time */
  const lastView = useRef("");
  const applyView = useCallback(
    (id: string, fromUrl = false) => {
      const st = storyById(id);
      if (!st) return;
      const g = useGraphUi.getState();
      g.applyStory(id);
      setNote("");
      if (st.seed) {
        // the seed and one hop out — but a view forces its pages past the type filter, so keep the hop to
        // the story's own types (otherwise a person's 900 blog posts would flood the thesis spine)
        const seed = st.seed.filter((s) => byId.has(s));
        const view = makeView("picked", st.headline?.label ?? st.name, seed, byId, neighbors);
        const types = new Set<string>(st.types);
        useGraphUi.setState({
          view: view ? { ...view, shown: new Set([...view.shown].filter((id) => view.hits.has(id) || types.has(byId.get(id)?.type ?? ""))) } : null,
        });
      }
      useKb.getState().clearSelection();
      if (st.tool) {
        const ex = useExperiments.getState();
        if (st.tool.flag && !ex.on.has(st.tool.flag)) ex.toggle(st.tool.flag);
        useGraphUi.setState({ flyout: st.tool.id, railOpen: false });
      } else if (g.flyout && TOOLS.some((t) => t.id === g.flyout)) {
        useGraphUi.setState({ flyout: null });
      }
      g.fit();
      lastView.current = id;
      if (!fromUrl) host.setParams({ view: id, search: undefined, pages: undefined, scope: undefined });
    },
    [byId, neighbors, host],
  );

  // ---- deep links: ?focus ?select ?search ?pages ?scope ?layer, applied once per distinct value
  const applied = useRef("");
  /** a snapshot's default view (`KB_EMBEDDED.home.view`) stands in for a missing `?view=` on the first pass only */
  const homeViewTried = useRef(false);
  useEffect(() => {
    const key = JSON.stringify([search.focus, search.select, search.search, search.pages, search.scope, search.layer, search.raw, search.view]);
    if (applied.current === key) return;
    applied.current = key;
    const view = homeViewTried.current ? (search.view && storyById(search.view) ? search.view : undefined) : initialView(search);
    homeViewTried.current = true;
    if (view && view !== lastView.current) applyView(view, true);
    if (search.raw === "1" && dsKind !== "embedded") useLayer.getState().setRaw(true);
    if (search.layer && search.layer in LAYER_TYPES) {
      useGraphUi.setState({ shownTypes: new Set<string>(LAYER_TYPES[search.layer as Layer]) });
    }
    if (search.search) void showMentions(search.search);
    else if (search.pages) showPicked(parsePages(search.pages), search.from === "home");
    else if (search.scope) {
      const slug = search.scope;
      void ds
        .getScope(slug)
        .then((d) => setView(makeView("scope", slug, scopeIds(slug, d.projection), byId, neighbors), `Scope ${slug} has no pages in the graph.`))
        .catch((e) => setNote(`Could not load scope ${slug}: ${e instanceof Error ? e.message : String(e)}`));
    }
    if (search.select) useKb.getState().setSelection(parsePages(search.select).filter((id) => byId.has(id)));
    // a Home subgraph is fitted whole by the canvas (refit on a new view); zooming onto the focus would crop it
    if (search.focus && byId.has(search.focus) && !(search.from === "home" && search.pages)) useGraphUi.getState().requestFocus(search.focus);
  }, [search, ds, dsKind, byId, neighbors, showMentions, showPicked, setView, applyView]);

  // ---- actions shared by the menu, the inspector, the finder and the keyboard
  const openReader = useCallback((id: string) => useGraphUi.setState({ readerSlug: id }), []);
  const focus = useCallback((id: string, zoom = true) => useGraphUi.getState().requestFocus(id, zoom), []);
  const closePanels = useCallback(() => {
    useGraphUi.setState({ readerSlug: null, detailsOpen: false });
  }, []);
  const selected = useMemo(() => [...selection].map((id) => byId.get(id)).filter((n): n is GNode => !!n), [selection, byId]);
  const closeMenu = useCallback(() => setMenu(null), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const st = useGraphUi.getState();
      if (e.key === "Escape") {
        if (isTyping(e.target)) return;
        if (st.readerSlug) st.set({ readerSlug: null });
        else if (st.detailsOpen) st.set({ detailsOpen: false });
        else if (st.flyout) st.set({ flyout: null });
        else if (useKb.getState().selection.size) useKb.getState().clearSelection();
        return;
      }
      if (isTyping(e.target)) return;
      const onButton = e.target instanceof HTMLElement && e.target.matches("button, a, summary");
      if (e.key === " " && !onButton) {
        e.preventDefault();
        const el = document.getElementById(FINDER_ID) as HTMLInputElement | null;
        if (el) {
          el.value = "";
          el.focus();
        }
      } else if (e.key === "/") {
        e.preventDefault();
        document.getElementById(FINDER_ID)?.focus();
      } else if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        st.fit();
      } else if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        canvas.current?.zoomBy(1.25);
      } else if (e.key === "-") {
        e.preventDefault();
        canvas.current?.zoomBy(1 / 1.25);
      } else if ((e.key === "e" || e.key === "E") && useKb.getState().selection.size === 1) {
        host.openPage([...useKb.getState().selection][0] as string);
      }
      const tool = TOOLS.find((t) => t.shortcut === e.key && flagOn(t.flag, useExperiments.getState().on));
      if (tool) st.openFlyout(tool.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [host]);

  const toolContext = useMemo<GraphToolContext>(
    () => ({
      model,
      byId,
      visible,
      selection,
      select: (ids, opts) => {
        const list = [...ids].filter((id) => byId.has(id));
        const kb = useKb.getState();
        kb.setSelection(opts?.additive ? [...kb.selection, ...list] : list);
      },
      clearSelection: () => useKb.getState().clearSelection(),
      focus,
      screenOf: (id) => canvas.current?.screenOf(id) ?? null,
      openReader,
    }),
    [model, byId, visible, selection, focus, openReader],
  );

  const menuNode = menu ? byId.get(menu.id) : undefined;
  const reader = ui.readerSlug ? byId.get(ui.readerSlug) : undefined;
  const showDetails = ui.detailsOpen && selected.length > 0;

  const legend = (
    <Legend nodes={model.nodes} visible={visible} schema={schema} shownTypes={shownTypes} stats={stats} quickHidden={filtered.size - visible.size} selected={selection.size} />
  );
  // the header's slot is looked up after the shell committed (a render-time lookup can run before it exists)
  const [headerSlot, setHeaderSlot] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => setHeaderSlot(document.getElementById(HEADER_SLOT_ID)), []);
  const finder = (
    <Finder
      nodes={model.nodes}
      byId={byId}
      colorBy={ui.colorBy}
      visible={visible}
      onFocus={(id) => (visible.has(id) ? focus(id) : showPicked([id]))}
      onRead={openReader}
      onShowPicked={showPicked}
      onShowMentions={(query) => void showMentions(query)}
      placement={headerSlot ? "header" : "canvas"}
    />
  );

  return (
    <HostContext.Provider value={host}>
      <div className="absolute inset-0" data-testid="graph-area">
      <GraphCanvas
        ref={canvas}
        model={model}
        byId={byId}
        neighbors={neighbors}
        visible={visible}
        imp={imp}
        className="absolute inset-0"
        onOpenMenu={(id, x, y) => setMenu({ id, x, y })}
        onBackgroundContext={(x, y) => {
          closeMenu();
          closePanels();
          useKb.getState().clearSelection();
          setBgMenu({ x, y });
        }}
        onOpenReader={openReader}
        onOpenPile={(format) => useLayer.getState().openDrawer({ kind: "format", format })}
      />
      {/* the search box lives in the app header when there is one (the embed has none: it floats over the canvas) */}
      {headerSlot ? createPortal(finder, headerSlot) : finder}
      <ViewsBar model={model} visible={visible} onPick={applyView} />
      {(ui.view || note) && (
        <div className={cn("pointer-events-auto absolute left-1/2 z-10 flex max-w-[min(28rem,calc(100%-8rem))] -translate-x-1/2 items-center gap-2 rounded-lg border bg-card px-2.5 py-1 text-xs shadow-[var(--shadow)]", headerSlot ? "top-14" : "top-24")} role="status">
          <span className="min-w-0 truncate">
            {ui.view ? (
              <>
                <b>{ui.view.hits.size}</b>{" "}
                {ui.view.kind === "search"
                  ? `page${ui.view.hits.size === 1 ? "" : "s"} mentioning “${ui.view.label}”`
                  : ui.view.kind === "scope"
                    ? `pages in ${ui.view.label}`
                    : ui.story && storyById(ui.story)?.seed
                      ? `pages on the ${ui.view.label.toLowerCase()} spine`
                      : `picked page${ui.view.hits.size === 1 ? "" : "s"}`}{" "}
                {ui.view.shown.size > ui.view.hits.size && <span className="text-muted-foreground">+ neighbours</span>}
              </>
            ) : (
              note
            )}
          </span>
          <button type="button" className="shrink-0 rounded px-1 hover:bg-accent" aria-label="Clear view" onClick={clearView}>
            ×
          </button>
        </div>
      )}
      <Toolbar
        onFit={() => ui.fit()}
        onZoom={(f) => canvas.current?.zoomBy(f)}
        onReheat={() => canvas.current?.reheat()}
        onRefresh={onRefresh}
        refreshing={refreshing}
        stats={stats}
        toolContext={toolContext}
        onBack={search.from === "home" ? () => (window.history.length > 1 ? window.history.back() : host.go("/")) : undefined}
      />
      {legend}
      {ui.railOpen && <LabRail imp={imp} selected={selected} className={cn("absolute bottom-16 left-14 top-3 z-20", wide ? "w-72" : "w-[min(20rem,calc(100%-4.5rem))]")} />}
      {/* the hover card is the quick peek; the inspector and the reader are where a page is read, so it yields to them */}
      {!ui.railOpen && !showDetails && !reader && <HoverCard byId={byId} className="absolute bottom-16 left-14 z-20" />}
      {bgMenu && (
        <div
          role="menu"
          aria-label="Graph"
          className="pointer-events-auto fixed z-50 min-w-40 rounded-lg border bg-popover p-1 text-sm shadow-[var(--shadow)]"
          style={{ left: bgMenu.x, top: bgMenu.y }}
          onMouseLeave={() => setBgMenu(null)}
        >
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded px-2 py-1 text-left hover:bg-accent"
            title="Push the pages around this point apart, gently; the layout settles and stays"
            onClick={() => {
              canvas.current?.spreadAt(bgMenu.x, bgMenu.y);
              setBgMenu(null);
            }}
          >
            Spread here
          </button>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded px-2 py-1 text-left hover:bg-accent"
            onClick={() => {
              ui.set({ fitTick: ui.fitTick + 1 });
              setBgMenu(null);
            }}
          >
            Fit to view
          </button>
        </div>
      )}
      {selected.length > 0 && !showDetails && !reader && (
        <div data-tour="graph-selection" className="pointer-events-auto absolute bottom-14 left-1/2 [.gt-active_&]:bottom-24 z-10 flex -translate-x-1/2 items-center gap-1 rounded-full border bg-card px-3 py-1 text-sm shadow-[var(--shadow)]">
          <span>{selected.length === 1 ? (selected[0]?.title || selected[0]?.id) : `${selected.length} selected`}</span>
          <Button size="sm" variant="ghost" onClick={() => ui.set({ detailsOpen: true })}>
            Details
          </Button>
          {!IS_SHARE && (
            <Button size="sm" variant="ghost" onClick={() => useChatDock.getState().ask(askAbout(selected))}>
              Ask
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => useKb.getState().clearSelection()}>
            Clear
          </Button>
        </div>
      )}
      {showDetails && (
        <Inspector
          nodes={selected}
          byId={byId}
          neighbors={neighbors}
          colorBy={ui.colorBy}
          revealed={ui.revealed}
          pageHref={host.pageHref}
          onClose={() => ui.set({ detailsOpen: false })}
          onClear={() => useKb.getState().clearSelection()}
          onFocus={focus}
          onRead={openReader}
          onToggleSources={(ids) => ui.toggleReveal(ids)}
        />
      )}
      {reader && <SideReader slug={reader.slug ?? reader.id} kb={host.foreignKb?.(reader.id)} title={reader.title || reader.id} pageHref={host.pageHref(reader.id)} onClose={() => ui.set({ readerSlug: null })} />}
      {menu && menuNode && (
        <NodeMenu
          node={menuNode}
          x={menu.x}
          y={menu.y}
          colorBy={ui.colorBy}
          onClose={closeMenu}
          ctx={{
            openReader,
            openPage: host.openPage,
            openDetails: (id) => {
              if (!useKb.getState().selection.has(id)) useKb.getState().setSelection([id]);
              useGraphUi.setState({ detailsOpen: true });
            },
          }}
        />
      )}
      {visibleTools.map((t) => (
        <div key={t.id}>{t.overlay?.(toolContext)}</div>
      ))}
      </div>
    </HostContext.Provider>
  );
}

