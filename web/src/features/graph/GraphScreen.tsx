import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";
import { createPortal } from "react-dom";
import { useDataSource } from "@/api";
import { useHeaderFolded } from "@/app/headerFold";
import { HEADER_SLOT_ID } from "@/app/headerSlot";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { IS_SHARE } from "@/share/env";
import { useKb } from "@/lib/store";
import { useApiQuery } from "@/lib/useApiQuery";
import type { GraphSearch } from "@/routes/search";
import { swatchColor } from "./nodeColor";
import { Finder, FINDER_ID } from "./Finder";
import { HostContext, type ToolHost } from "./hostContext";
import { useLayer } from "./layerStore";
import "./tools/register";
import { askAbout, useChatDock } from "./tools/chatDockStore";
import "./directions/register";
import { extendView, makeView, parsePages, scopeIds, type GraphView } from "./pageSearch";
import { buildNeighborMap } from "./graphData";
import { GraphCanvas, type CanvasHandle } from "./GraphCanvas";
import { Inspector } from "./Inspector";
import { computeImportance } from "./lab/importance";
import { HoverCard } from "./lab/HoverCard";
import { LabRail } from "./lab/LabRail";
import { DIVE_PARAMS, initialView } from "./defaultView";
import { CALM_STORY, DEFAULT_STORY, isCalmStory, storyById, storyKnown, storyOffered, storyTypes } from "./lab/views";
import { viewCards, type ViewCard } from "./shell/corners/panelModel";
import { applySpecV1 } from "./shell/corners/viewSpec";
import { Legend } from "./Legend";
import { predicateFn } from "./publicPredicate";
import { ViewsBar } from "./views/ViewsBar";
import { NodeMenu } from "./NodeMenu";
import { applyQuick } from "./quickFilters";
import { computeVisible } from "./rules";
import { assignAreaColors, colorKey, effectiveColorBy } from "./style";
import { registerTypeMarks } from "./encoding/spec";
import { parseSchema, withDataTypes } from "./schema";
import { SideReader, type ReaderStep } from "./SideReader";
import { useGraphUi } from "./store";
import { Panels } from "./Panels";
import { Corners } from "./shell/corners/Corners";
import { parseKbs } from "@/lib/kbSelection";
import { useFlag } from "@/flags/useFlag";
import { relationIndex } from "./relationGroups";
import { TOOLS, toolOn, useVisibleTools, type GraphToolContext } from "./tools";
import { useExperiments } from "./tools/experiments";
import { toModel, type GNode } from "./types";
import { LAYER_TYPES, type Layer } from "@/api/model";
import "./tours";
import { GraphShell } from "./shell/GraphShell";
import { HeaderFold } from "./shell/HeaderFold";
import { ChatExplorer } from "./shell/ChatExplorer";
import { ChatRail } from "./shell/ChatRail";
import { BUSY_NOTICE, useChatFull } from "./shell/chatFullStore";
import { defaultFetch } from "./shell/corners/api";
import { loadSession, newChat } from "./shell/corners/sessions";
import { readJson } from "@/features/chat/storage";
import { FULL_PANE_W, SPARK_PANEL_W, chatPanelWidth, useShellTop } from "./shell/layout";
import { useFullChat } from "./shell/useFullChat";
import { chatInPanel, useSparkPanel } from "./shell/sparkPanelStore";
import { SparkPanelHost, useSparkOpen } from "./shell/SparkPanelHost";

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
  // which knowledge bases (the header menu writes `?kbs=`): [] = the server's own; `none` = nothing picked
  const picked = kbViewOn ? parseKbs(search.kbs) : null;
  const noneShown = picked !== null && !picked.length;
  const kbs = useMemo(() => picked ?? [], [picked?.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  // `?chat=` (flag chat-full): /chat and /chat/<id> land here; the full chat opens on that chat, then the param goes
  const chatFull = useFlag("chat-full");
  const sparkChat = useFlag("spark-chat");
  const chatFlag = chatFull && sparkChat;
  const chatParam = search.chat;
  const askParam = search.ask;
  useEffect(() => {
    if (!chatParam || !chatFlag || !chatInPanel()) return;
    let live = true;
    void (async () => {
      // an open panel is never remounted for nothing: a remount aborts a streaming answer and drops the draft
      const panel = useSparkPanel.getState();
      const store = useChatFull.getState();
      const plain = (id: string) => id.replace(/^kb-chat:/, "");
      const here = readJson<{ id?: string } | null>("session", "kbchat.chat", null)?.id;
      const stay = (note: string) => store.setNotice(note);
      let remount = !panel.open;
      if (chatParam === "new") {
        if (panel.open && store.busy) stay(BUSY_NOTICE);
        else {
          newChat();
          remount = false;
        }
      } else if (chatParam !== "open" && !(panel.open && here && plain(here) === plain(chatParam))) {
        if (panel.open && store.busy) stay(BUSY_NOTICE);
        else {
          try {
            await loadSession(defaultFetch, chatParam);
            remount = true;
          } catch {
            // an id the server does not know must not show whatever chat the browser held last
            newChat();
            remount = false;
            store.setNotice("That chat was not found, so this is a new one.");
          }
        }
      }
      if (!live) return;
      store.setFull(true);
      if (askParam) {
        if (panel.open) store.insertText(askParam);
        else useChatDock.getState().ask(askParam);
      } else if (remount) panel.show();
      host.clearParams(["chat", "ask"]);
    })();
    return () => {
      live = false;
    };
  }, [chatParam, askParam, chatFlag]); // eslint-disable-line react-hooks/exhaustive-deps
  // the data layer is the server's own knowledge base's: it is off while other knowledge bases are shown
  const rawOn = useLayer((s) => s.rawOn) && ds.kind !== "embedded" && !kbs.length;
  const q = useApiQuery(["graph", rawOn, kbs.join(",")], (d) => d.getGraph({ ...(rawOn ? { raw: true } : {}), ...(kbs.length ? { kbs } : {}) }), {
    enabled: !noneShown,
    refetchInterval: live ? (rawOn ? LIVE_RAW_MS : LIVE_MS) : false,
    // switching the data layer on or off keeps the canvas (and its positions) until the new snapshot lands
    placeholderData: keepPreviousData,
  });
  const snap = q.data;

  // The model is rebuilt only when the wiki changed (etag), not on every poll.
  const etag = snap?.etag;
  const model = useMemo(() => (snap ? toModel(snap) : null), [etag, snap?.layer]); // eslint-disable-line react-hooks/exhaustive-deps
  // the kit's types, plus any type the pages carry that the kit does not define (an imported OKF bundle's), so the
  // Map, the legend and the marks treat them as real types
  const schema = useMemo(() => {
    const inData = (snap?.nodes ?? []).map((n) => n.type);
    const s = withDataTypes(parseSchema(snap?.schema), inData);
    // marks go to the types this kb has, so its first own concept type takes the first free symbol
    const present = new Set(inData);
    registerTypeMarks(s.types.filter((t) => present.has(t.id)));
    return s;
  }, [etag]); // eslint-disable-line react-hooks/exhaustive-deps
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

  if (noneShown)
    return (
      <FullBleed>
        <div className="p-4">
          <Empty>No knowledge base is shown. Pick one from the menu on the knowledge base name, top left.</Empty>
        </div>
      </FullBleed>
    );
  if (q.isLoading) return <FullBleed><div className="p-4"><Loading label="Loading graph" rows={4} /></div></FullBleed>;
  if (q.isError || !snap || !model)
    return (
      <FullBleed>
        <div className="p-4">
          <ErrorState title="Could not load the graph." error={q.error} onRetry={() => void q.refetch()} />
        </div>
      </FullBleed>
    );
  if (!model.nodes.length)
    return (
      <FullBleed>
        <div className="p-4"><Empty>The vault has no pages yet.</Empty></div>
      </FullBleed>
    );
  return (
    <FullBleed>
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

/** The screen sits under the 48px header and fills the rest of the viewport (the graph needs the room); while the bar is folded away (flag header-fold) it takes the whole viewport. */
function FullBleed({ children }: { children: React.ReactNode }) {
  const folded = useHeaderFolded();
  return (
    <div
      className={cn("fixed inset-x-0 bottom-0 z-30 overflow-hidden bg-background transition-[top] duration-200 motion-reduce:transition-none", folded ? "top-0" : "top-12")}
      data-testid="graph-screen"
      data-header-folded={folded || undefined}
    >
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
  const shell = useFlag("graph-shell");
  const headerFold = useFlag("header-fold");
  const calm = useFlag("calm-graph");
  // flag calm-graph, first visit: the default is set before the first render builds the canvas, so nothing moves
  // after the first frame (an effect would apply it a frame late and relayout). A late flag is handled below.
  const firstBare = useRef(!search.view && !search.layer && !DIVE_PARAMS.some((k) => search[k] !== undefined && search[k] !== "") && initialView(search) === undefined);
  const calmDone = useRef(false);
  if (calm && !calmDone.current) {
    calmDone.current = true;
    if (firstBare.current && useGraphUi.getState().story === DEFAULT_STORY) useGraphUi.getState().applyStory(CALM_STORY);
  }
  const shellTop = useShellTop();
  const sparkOpen = useSparkOpen();
  const { full: fullChat, folded: foldedChat } = useFullChat();
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
  const relations = useMemo(() => (model.relations ? relationIndex(model.relations) : undefined), [model]);
  const shownTypes = useMemo(() => {
    if (ui.shownTypes !== undefined) return ui.shownTypes;
    // a view that names layers (Map) draws those layers of this kb's own schema, whatever its kit
    return storyTypes(storyById(ui.story), schema) ?? new Set(schema.defaultVisible);
  }, [ui.shownTypes, ui.story, schema]);
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
        const types = new Set<string>(st.types ?? []);
        useGraphUi.setState({
          view: view ? { ...view, shown: new Set([...view.shown].filter((id) => view.hits.has(id) || types.has(byId.get(id)?.type ?? ""))) } : null,
        });
      }
      useKb.getState().clearSelection();
      if (st.tool && storyOffered(st)) {
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

  // flag calm-graph: the switcher's views are the pinned panel's cards; a pick applies like a card click
  const calmViews = useMemo<ViewCard[] | undefined>(() => (calm ? viewCards(model.nodes, schema) : undefined), [calm, model.nodes, schema]);
  const pickView = useCallback((card: ViewCard) => void applySpecV1(card.spec, { applyView, showPicked }), [applyView, showPicked]);

  // flag calm-graph: a bare first visit on the untouched default opens on Concepts (sources hidden until the Sources view).
  // It follows the flag, which may arrive after the first render; a calm view left over from a time the flag was on
  // never applies while it is off (back to today's default). Set straight on the store: a tool panel or selection
  // a link opened is left alone.
  /** the calm view set aside while the flag was (not yet) on: it comes back if the flag arrives late */
  const heldCalm = useRef("");
  useEffect(() => {
    const g = useGraphUi.getState();
    if (!calm) {
      if (isCalmStory(g.story)) {
        heldCalm.current = g.story;
        g.applyStory(DEFAULT_STORY);
      }
      return;
    }
    if (calmDone.current) return;
    calmDone.current = true;
    if (heldCalm.current) {
      g.applyStory(heldCalm.current);
      g.fit();
      return;
    }
    if (firstBare.current && g.story === DEFAULT_STORY) {
      g.applyStory(CALM_STORY);
      g.fit();
    }
  }, [calm]);

  // ---- deep links: ?focus ?select ?search ?pages ?scope ?layer, applied once per distinct value
  const applied = useRef("");
  /** a snapshot's default view (`KB_EMBEDDED.home.view`) stands in for a missing `?view=` on the first pass only */
  const homeViewTried = useRef(false);
  useEffect(() => {
    const key = JSON.stringify([search.focus, search.select, search.search, search.pages, search.scope, search.layer, search.raw, search.view]);
    if (applied.current === key) return;
    applied.current = key;
    const view = homeViewTried.current ? (search.view && storyKnown(search.view) ? search.view : undefined) : initialView(search);
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

  // ?tool=<id> opens that tool once (links into the folded Relations and Scopes screens land here)
  useEffect(() => {
    if (search.tool) useGraphUi.setState({ flyout: search.tool, railOpen: false });
  }, [search.tool]);

  // ---- actions shared by the menu, the inspector, the finder and the keyboard
  const openReader = useCallback((id: string) => useGraphUi.setState((s) => ({ readerSlug: id, readerSet: s.readerSet.includes(id) ? s.readerSet : [] })), []);
  const readerStep = useMemo<ReaderStep | undefined>(() => {
    const at = ui.readerSlug ? ui.readerSet.indexOf(ui.readerSlug) : -1;
    if (at < 0 || ui.readerSet.length < 2) return undefined;
    return {
      index: at + 1,
      total: ui.readerSet.length,
      go: (d) => {
        const next = ui.readerSet[at + d];
        if (next) useGraphUi.setState({ readerSlug: next });
      },
    };
  }, [ui.readerSlug, ui.readerSet]);
  const focus = useCallback((id: string, zoom = true) => useGraphUi.getState().requestFocus(id, zoom), []);
  const closePanels = useCallback(() => {
    useGraphUi.setState({ readerSlug: null, detailsOpen: false });
  }, []);
  const selected = useMemo(() => [...selection].map((id) => byId.get(id)).filter((n): n is GNode => !!n), [selection, byId]);
  const closeMenu = useCallback(() => setMenu(null), []);

  // the empty-space menu closes like any menu: Escape (even from the search line) or a press outside it
  const bgMenuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!bgMenu) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setBgMenu(null);
    };
    const onDown = (e: PointerEvent) => {
      if (!(e.target instanceof Node && bgMenuRef.current?.contains(e.target))) setBgMenu(null);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown, true);
    };
  }, [bgMenu]);

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
      const tool = TOOLS.find((t) => t.shortcut === e.key && toolOn(t, useExperiments.getState().on));
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

  // flag chat-full: the composer completes @pages from this graph, and a node clicked while the chat is full lands in it
  const chatOn = useFlag("chat-full");
  useEffect(() => {
    if (!chatOn) return;
    useChatFull.getState().setPages(model.nodes.map((n) => ({ id: n.id, title: n.title || n.id })));
    return () => useChatFull.getState().setPages([]);
  }, [chatOn, model]);
  const lastPicked = useRef<string | null>(null);
  useEffect(() => {
    const id = selection.size === 1 ? [...selection][0]! : null;
    if (id && id !== lastPicked.current && fullChat) useChatFull.getState().mentionPage(id, byId.get(id)?.title || id);
    lastPicked.current = id;
  }, [selection, fullChat, byId]);
  const railColors = useMemo(() => {
    const seen = new Set<string>();
    for (const n of model.nodes) {
      seen.add(swatchColor(n, ui.colorBy));
      if (seen.size >= 5) break;
    }
    return [...seen];
  }, [model, ui.colorBy]);

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
      {/* the full chat leaves the canvas the top of the right pane */}
      <div className="absolute" style={fullChat ? { left: chatPanelWidth(true, false), right: 0, top: 0, bottom: "50%" } : { inset: 0 }}>
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
      </div>
      {/* the search box lives in the app header when there is one (the embed has none: it floats over the canvas) */}
      {shell ? (
        // the search line and the corner controls share one frame: it narrows while the side reader is open, so the reader never covers them
        // (the full chat folds the whole frame away with its right pane: the graph is not on show)
        <div
          className="pointer-events-none absolute top-0 transition-[left,right] duration-200 motion-reduce:transition-none"
          hidden={foldedChat}
          style={{
            left: fullChat ? chatPanelWidth(true, false) : sparkOpen ? SPARK_PANEL_W : 0,
            right: reader && !fullChat ? "min(34rem, 100%)" : 0,
            bottom: fullChat ? "50%" : 0,
          }}
        >
          {headerFold && <HeaderFold />}
          <GraphShell
            nodes={model.nodes}
            links={model.links}
            byId={byId}
            colorBy={ui.colorBy}
            onFocus={(id) => (visible.has(id) ? focus(id) : showPicked([id]))}
            onRead={openReader}
            onShowExact={(ids) => showPicked(ids, true)}
            shownTypes={shownTypes}
            onShowMentions={(query) => void showMentions(query)}
            onFit={() => ui.fit()}
            onZoom={(f) => canvas.current?.zoomBy(f)}
            onReheat={() => canvas.current?.reheat()}
            onRefresh={onRefresh}
            setParams={host.setParams}
            top={shellTop}
            views={calmViews}
            onPickView={pickView}
          />
          <Corners nodes={model.nodes} visible={visible} schema={schema} shownTypes={shownTypes} stats={stats} host={host} applyView={applyView} showPicked={showPicked} />
        </div>
      ) : headerSlot ? (
        createPortal(finder, headerSlot)
      ) : (
        finder
      )}
      {!shell && <ViewsBar model={model} visible={visible} onPick={applyView} />}
      {(ui.view || note) && (
        <div className={cn("pointer-events-auto absolute left-1/2 z-10 flex max-w-[min(28rem,calc(100%-8rem))] -translate-x-1/2 items-center gap-2 rounded-lg border bg-card px-2.5 py-1 text-xs shadow-[var(--shadow)]", shell ? "top-32" : headerSlot ? "top-14" : "top-24")} role="status">
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
      <Panels
        onReheat={() => canvas.current?.reheat()}
        onRefresh={onRefresh}
        refreshing={refreshing}
        stats={stats}
        toolContext={toolContext}
      />
      {!shell && legend}
      {ui.railOpen && <LabRail imp={imp} selected={selected} className={cn("absolute bottom-[66px] left-3.5 top-[66px] z-20", wide ? "w-72" : "w-[min(20rem,calc(100%-2rem))]")} />}
      {/* the hover card is the quick peek; the inspector and the reader are where a page is read, so it yields to them */}
      {!ui.railOpen && !showDetails && !reader && <HoverCard byId={byId} className="absolute bottom-[66px] left-3.5 z-20" />}
      {bgMenu && (
        <div
          ref={bgMenuRef}
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
          relations={relations}
          clearOfEdge={shell}
        />
      )}
      {reader && !fullChat && <SideReader slug={reader.slug ?? reader.id} kb={host.foreignKb?.(reader.id)} title={reader.title || reader.id} pageHref={host.pageHref(reader.id)} onClose={() => ui.set({ readerSlug: null, readerSet: [] })} step={readerStep} />}
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
      {shell && <SparkPanelHost scope={search.scope} />}
      {fullChat && !foldedChat && (
        <>
          <div className="absolute bottom-0 right-0 z-30 h-1/2" style={{ width: FULL_PANE_W }}>
            <ChatExplorer
              byId={byId}
              colorBy={ui.colorBy}
              slug={ui.readerSlug}
              onPick={openReader}
              pageHref={(slug) => host.pageHref(slug)}
              onClose={() => ui.set({ readerSlug: null })}
            />
          </div>
          <button
            type="button"
            aria-label="Fold the graph pane"
            title="Fold the graph pane"
            onClick={() => useChatFull.getState().setFolded(true)}
            className="group pointer-events-auto absolute top-1/4 z-[41] grid h-12 w-6 -translate-y-1/2 place-items-center focus-visible:outline-none"
            style={{ left: chatPanelWidth(true, false) }}
          >
            {/* the hit target is 24px wide; the tab you see stays slim */}
            <span className="grid h-12 w-4 place-items-center rounded-r-md border border-l-0 bg-card text-muted-foreground shadow-[var(--shadow)] group-hover:text-foreground group-focus-visible:ring-2 group-focus-visible:ring-ring">
              <ChevronRight aria-hidden className="size-3.5" strokeWidth={1.8} />
            </span>
          </button>
        </>
      )}
      {foldedChat && <ChatRail colors={railColors} />}
      {visibleTools.map((t) => (
        <div key={t.id}>{t.overlay?.(toolContext)}</div>
      ))}
      </div>
    </HostContext.Provider>
  );
}

