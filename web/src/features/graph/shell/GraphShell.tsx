import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "@tanstack/react-router";
import {
  ArrowRightLeft,
  CircleHelp,
  CornerDownRight,
  Feather,
  History,
  Layers,
  LayoutGrid,
  ListFilter,
  Maximize,
  MessageSquare,
  Network,
  Pin,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Star,
  Undo2,
  Wand2,
  Wind,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useDataSource, type PinnedView, type RecentStep } from "@/api";
import { useFlag } from "@/flags/useFlag";
import { useKb } from "@/lib/store";
import { useApiQuery } from "@/lib/useApiQuery";
import { useCapabilities } from "./capabilities";
import { NodeSwatch } from "../encoding/NodeMarkSvg";
import { useToolHost } from "../hostContext";
import type { ColorBy } from "../style";
import { swatchColor } from "../nodeColor";
import { useGraphUi } from "../store";
import { useChatDock } from "../tools/chatDockStore";
import { chatContextDraft } from "./chatContext";
import { useVisibleTools } from "../tools";
import type { GLink, GNode } from "../types";
import { Chips } from "../layers/Chips";
import { makeLayer, newLayerId, type Layer, type ViewStack } from "../layers/model";
import { ResolvedLine } from "../layers/ResolvedLine";
import { needsMeaning } from "../layers/meaning";
import { anchorLayers, applyLayers, isAnchored, readyCard, specLayers, stackLines, type ReadyCard } from "../layers/readyViews";
import { Gallery } from "../views/Gallery";
import { useGallery } from "../views/galleryStore";
import { useLayers } from "../layers/store";
import { openCaptureAbout } from "../captureAbout";
import { useLlmLayers } from "../layers/useLlmLayers";
import { ACTION_ITEMS, setActionItems, type MenuContext } from "../menu";
import { NodeMenu } from "../NodeMenu";
import { exportPages } from "../export/runExport";
import { planSentence, type Plan } from "../layers/sentenceRun";
import { buildCommands, closestCommands, filterCommands, GROUP_ORDER, type Command, type CommandIcon } from "./commands";
import { LINE_COPY, type LineMode } from "./copy";
import { useMeaningHits } from "./useMeaningHits";
import { SearchBar } from "./SearchBar";
import { optionId, SearchPanel, type PanelRow, type PanelStatus, type ViewChoice } from "./SearchPanel";
import { activeCard, type ViewCard } from "./corners/panelModel";
import { marker, pillText, sameMarker } from "./shape";
import { looksLikeShape, parseMode, requestShape, useShellStore } from "./shellStore";
import { useShape } from "./useShape";
import { usePageResults } from "./usePageResults";
import { useTextHits } from "./useTextHits";
import { defaultFetch } from "./corners/api";
import { loadSession, showDock } from "./corners/sessions";
import { formatOfPath } from "../corpusRows";
import { useLayer } from "../layerStore";
import { favoriteRows, groupedRows } from "./groupedRows";
import { useFavorites } from "../favorites/store";
import { buildSearchIndex, withNames, type RowTarget } from "./searchGroups";
import { SHELL_TOP } from "./layout";

const ICONS: Record<CommandIcon, ReactNode> = {
  fit: <Maximize aria-hidden className="size-4" strokeWidth={1.6} />,
  "zoom-in": <ZoomIn aria-hidden className="size-4" strokeWidth={1.6} />,
  "zoom-out": <ZoomOut aria-hidden className="size-4" strokeWidth={1.6} />,
  reheat: <Wind aria-hidden className="size-4" strokeWidth={1.6} />,
  refresh: <RefreshCw aria-hidden className="size-4" strokeWidth={1.6} />,
  labels: <SlidersHorizontal aria-hidden className="size-4" strokeWidth={1.6} />,
  filters: <ListFilter aria-hidden className="size-4" strokeWidth={1.6} />,
  layout: <Network aria-hidden className="size-4" strokeWidth={1.6} />,
  help: <CircleHelp aria-hidden className="size-4" strokeWidth={1.6} />,
  tool: null,
  kb: <ArrowRightLeft aria-hidden className="size-4" strokeWidth={1.6} />,
  go: <CornerDownRight aria-hidden className="size-4" strokeWidth={1.6} />,
  think: <Feather aria-hidden className="size-4" strokeWidth={1.6} />,
  favorite: <Star aria-hidden className="size-4" strokeWidth={1.6} />,
};

const NOTICE_MS = 3200;
const HINTS_KEY = "kb-graph-line-hints-v1";
const RECENT_SHOWN = 5;
const PAGES_SHOWN = 6;
const RELATED_SHOWN = 3;

interface Props {
  nodes: readonly GNode[];
  /** The links of the loaded graph (the layer model reads degree and hops from them; flag graph-intent). */
  links?: readonly GLink[];
  byId: ReadonlyMap<string, GNode>;
  colorBy: ColorBy;
  /** Enter on a page: centre on it (bringing it in when it is filtered out). */
  onFocus: (id: string) => void;
  /** Shift+Enter on a page: read it in the side reader. */
  onRead: (id: string) => void;
  /** Draw exactly these pages, replacing the pages on screen (free-text shaping). */
  onShowExact: (ids: string[]) => void;
  /** The types drawn now (free-text shaping hides some). */
  shownTypes: ReadonlySet<string> | null;
  /** "Show pages mentioning ...". */
  onShowMentions: (q: string) => void;
  onFit: () => void;
  onZoom: (factor: number) => void;
  onReheat: () => void;
  onRefresh: () => void;
  /** Merge params into the URL (the `kbs` param). */
  setParams?: (patch: Record<string, string | undefined>) => void;
  /** Top of the line inside the graph area (./layout). */
  top?: number;
  /** Flag calm-graph: the views that fit this kb (the cards of the pinned panel) and what picking one does. */
  views?: readonly ViewCard[];
  onPickView?: (card: ViewCard) => void;
}

/**
 * The calm shell of the graph (flag graph-shell): the search panel is the one command surface. A bar at top
 * centre unfolds, on focus or Cmd/Ctrl+K, into recent steps and pinned views at rest, live page results while
 * typing, commands after a slash, and two free-text rows (ask the agent, shape the graph).
 */
export function GraphShell({ nodes, links, byId, colorBy, onFocus, onRead, onShowExact, shownTypes, onShowMentions, onFit, onZoom, onReheat, onRefresh, setParams, top = SHELL_TOP, views, onPickView }: Props) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const host = useToolHost();
  const tools = useVisibleTools();
  const calm = useFlag("calm-graph");
  const intent = useFlag("graph-intent");
  const caps = useCapabilities();
  // meaning (flags graph-intent and semantic-search): a model call, so never on the share build or the embedded data
  const semantic = useFlag("semantic-search");
  const meaningOn = intent && semantic && caps.serverSearch && ds.kind !== "embedded";
  const kbViewOn = useFlag("kb-view") && ds.kind !== "embedded";
  const [raw, setRaw] = useState("");
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const notice = useShellStore((s) => s.notice);
  const shaping = useShellStore((s) => s.shaping);
  const shape = useShellStore((s) => s.shape);
  const shapeError = useShellStore((s) => s.shapeError);
  const canUndo = useShellStore((s) => s.undo !== null);
  const layersUndo = useLayers((s) => s.history.length > 0);
  const preview = useLayers((s) => s.preview);
  // the sentence (with its op) the preview answers; editing the text retires the preview
  const previewKey = useRef("");
  const [editingLine, setEditingLine] = useState(false);
  // the pill speaks only while the shape is what is drawn: a change by hand (a legend click, a cleared view) retires it
  const shapeCurrent = useGraphUi((s) => (shape ? sameMarker(shape.after, marker(s)) : false));
  const story = useGraphUi((s) => s.story);
  const recent = useGraphUi((s) => s.quick.recent);
  const rawNow = useRef("");
  rawNow.current = raw;
  const openRef = useRef(false);
  openRef.current = open;
  const intentRef = useRef(intent);
  intentRef.current = intent;

  // flag graph-intent: the favorite pages, read with the graph and again when the knowledge base changes
  const favs = useFavorites((s) => s.slugs);
  const favsLoaded = useFavorites((s) => s.loaded);
  // flag graph-intent: the layer store folds a stack onto this graph, so it needs the pages, the links and how to draw pages
  const pickRef = useRef(onPickView);
  pickRef.current = onPickView;
  const showRef = useRef(onShowExact);
  showRef.current = onShowExact;
  useEffect(() => {
    if (!intent) return;
    useLayers.getState().setGraph({
      nodes,
      links: links ?? [],
      favorites: favsLoaded ? favs : undefined,
      show: (ids) => showRef.current(ids),
      applyLegacy: (spec) => pickRef.current?.({ id: "legacy", name: "", count: "", spec }),
      similar: meaningOn ? async ({ q, slug, k }) => (await ds.searchSimilar({ q, slug, k })).hits.map((h) => h.slug) : undefined,
    });
    return () => useLayers.getState().setGraph(null);
  }, [intent, nodes, links, favs, favsLoaded, meaningOn, ds]);

  // a shared site cannot change the view by writing: `>` is dropped and the rest is searched (with one quiet line saying so)
  const sentenceBlocked = intent && !caps.sentences && raw.startsWith(">");
  const line = sentenceBlocked ? raw.replace(/^>[+-]?\s*/, "") : raw;
  const text = line.trim();
  const slash = line.startsWith("/");
  const parsed = parseMode(line);
  const viewMode = intent && caps.sentences && parsed.mode === "view";
  const [hintMode, setHintMode] = useState<LineMode | null>(null);
  // q3: a name that needs the user's pick before the sentence applies
  const [didYou, setDidYou] = useState<{ text: string; op: "replace" | "stack"; pick: Extract<Plan, { kind: "ask" }>["pick"]; chosen: Record<string, string> } | null>(null);

  // ---- data: recent steps and pinned views (rest), the knowledge bases (kb-view), page results (typing)
  const live = ds.kind !== "embedded";
  const recentQ = useApiQuery(["recent"], (d) => d.listRecent(), { enabled: live && caps.recentSteps, retry: false, staleTime: 5_000 });
  const viewsQ = useApiQuery(["views"], (d) => d.listViews(), { enabled: live || caps.readViews, retry: false, staleTime: 5_000 });
  // flag graph-intent: the kit's ready views (lines of the query language; each is read here, never by the server)
  const readyQ = useApiQuery(["views", "ready"], (d) => d.listReadyViews(), { enabled: (live || caps.readViews) && intent, retry: false, staleTime: 60_000 });
  const ready = useMemo<ReadyCard[]>(() => (readyQ.data?.views ?? []).map(readyCard), [readyQ.data]);
  const kbQ = useApiQuery(["kb"], (d) => d.getKb(), { staleTime: Infinity, retry: false });
  const kbListQ = useApiQuery(["kb-list"], (d) => d.listKbs(), { enabled: kbViewOn, staleTime: 30_000 });
  const results = usePageResults(nodes, byId, line, !slash && text.length > 0);
  const router = useRouter({ warn: false });
  const textHits = useTextHits(line, intent && caps.serverSearch && !slash && text.length > 0);
  const meaningHits = useMeaningHits(text, meaningOn && !slash && !viewMode);
  const meaning = useMemo(
    () => (meaningOn ? meaningHits.flatMap((h) => (byId.get(h.slug) ? [{ node: byId.get(h.slug)!, score: h.score }] : [])) : undefined),
    [meaningOn, meaningHits, byId],
  );
  const kbName = kbQ.data?.name ?? "Knowledge Base";
  useEffect(() => {
    if (intent && (live || caps.favoriteMark)) void useFavorites.getState().load();
  }, [intent, live, caps.favoriteMark, nodes, kbQ.data?.id]);
  // flag graph-intent: the tier-1 index, built once per graph load (page entries) and joined with the small name lists
  const baseIndex = useMemo(() => (intent ? buildSearchIndex(nodes) : null), [intent, nodes]);
  const [menu, setMenu] = useState<{ target: RowTarget; x: number; y: number } | null>(null);

  // first use of a mode shows its one-line hint (once ever per mode); Escape or the first Enter dismisses it
  const lineMode = parsed.mode;
  useEffect(() => {
    if (!intent || !open) return setHintMode(null);
    let seen: Record<string, boolean> = {};
    try {
      seen = JSON.parse(window.localStorage.getItem(HINTS_KEY) ?? "{}") ?? {};
    } catch {
      // storage unavailable: the hint shows for this visit only
    }
    if (seen[lineMode]) return setHintMode((m) => (m === lineMode ? m : null));
    setHintMode(lineMode);
    try {
      window.localStorage.setItem(HINTS_KEY, JSON.stringify({ ...seen, [lineMode]: true }));
    } catch {
      // ignore
    }
  }, [intent, open, lineMode]);

  const record = useCallback(
    (label: string, spec: Record<string, unknown>) => {
      if (!live || !caps.recentSteps) return;
      // re-running the same step must not fill the server's short history with copies
      const newest = recentQ.data?.recent.at(-1);
      if (newest && newest.text === label) return;
      ds.addRecent(label, spec).then((r) => qc.setQueryData(["recent"], r), () => {});
    },
    [ds, qc, live, caps.recentSteps, recentQ.data],
  );

  // ---- flag calm-graph: one switcher of views (open at rest) and a `/view` command for each
  const viewChoices = useMemo<ViewChoice[]>(() => {
    if (!calm || !views?.length || !onPickView) return [];
    const on = activeCard(views, { story, quick: { recent } });
    return views.map((v) => ({ id: v.id, name: v.name, count: v.count, active: v.id === on, run: () => (onPickView(v), close()) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calm, views, onPickView, story, recent]);

  const commands = useMemo(
    () =>
      buildCommands({
        onFit,
        onZoom,
        onReheat,
        onRefresh,
        tools,
        host,
        setParams,
        kbs: kbViewOn ? (kbListQ.data?.kbs ?? []).map((k) => ({ id: k.id, name: k.name, active: k.active, error: k.error })) : [],
        share: !caps.saveViews,
        intent,
        views: viewChoices,
      }),
    [onFit, onZoom, onReheat, onRefresh, tools, host, setParams, kbViewOn, kbListQ.data, viewChoices, intent],
  );

  const index = useMemo(
    () => (baseIndex ? withNames(baseIndex, viewsQ.data?.views ?? [], commands.map((c) => ({ id: c.id, label: c.label }))) : null),
    [baseIndex, viewsQ.data, commands],
  );

  // ---- open and close
  const close = useCallback((clear = true) => {
    setOpen(false);
    if (clear) setRaw("");
    input.current?.blur();
  }, []);
  const openPanel = useCallback(() => setOpen(true), []);
  const focusBar = useCallback((value?: string) => {
    if (value !== undefined) setRaw(value);
    setOpen(true);
    input.current?.focus();
  }, []);

  // flag graph-intent: a `>` sentence the rules cannot read is read by the model (POST /api/graph/layers)
  const llm = useLlmLayers({ nodes, onPlan: (plan, typed, op) => settleSentence(plan, typed, op, {}) });
  // an answer on its way is dropped when the panel closes
  const cancelLlm = llm.cancel;
  useEffect(() => {
    if (!open) cancelLlm();
  }, [open, cancelLlm]);
  const { undo, cancel } = useShape({
    byId,
    shownTypes,
    showExact: onShowExact,
    record,
    onApplied: (text, say) => {
      // the panel closes unless the person has moved on to other text meanwhile
      if (rawNow.current.trim() === text || (intentRef.current && parseMode(rawNow.current).text === text)) close();
      useShellStore.getState().say(say);
    },
  });
  const undoShape = useCallback(() => {
    // flag graph-intent: the layer stack keeps its own history (a shape is one step of it)
    if (intent && useLayers.getState().undo()) {
      cancel();
      useShellStore.getState().say("Undid the last change.");
    } else if (undo()) useShellStore.getState().say("Undid the last shape.");
  }, [undo, cancel, intent]);

  useEffect(() => {
    // Capture phase on the window: while this shell is mounted Cmd/Ctrl+K belongs to the search panel
    // (the global palette's listener comes later and never sees the event). Its "Go to" list is under "/".
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        e.stopPropagation();
        focusBar();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "z") {
        // Undo the last shape while the panel is closed and nothing is being typed (typing keeps the text's own undo)
        const t = e.target;
        const typing = t instanceof HTMLElement && t.closest("input, textarea, select, [contenteditable]");
        if (!typing && !openRef.current && (useShellStore.getState().undo || (intentRef.current && useLayers.getState().history.length))) {
          e.preventDefault();
          undoShape();
        }
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
      const t = e.target;
      // typing, or a control that owns the key (a menu item, tab, checkbox, anything inside a dialog or menu)
      if (t instanceof HTMLElement && t.closest("input, textarea, select, [contenteditable], [role=menu], [role=dialog], [role=menuitem], [role=tab], [role=checkbox], [role=switch], [role=option]")) return;
      if (e.key === "/") {
        e.preventDefault();
        focusBar("/");
      } else if (e.key === " " && !(t instanceof HTMLElement && t.matches("button, a, summary"))) {
        e.preventDefault();
        focusBar("");
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [focusBar, undoShape]);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node) && !(e.target as HTMLElement | null)?.closest?.("[role=menu]")) close(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open, close]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => useShellStore.getState().dismissNotice(), NOTICE_MS);
    return () => window.clearTimeout(t);
  }, [notice]);

  // ---- rows
  const rows = useMemo<PanelRow[]>(() => {
    const out: PanelRow[] = [];
    const done = (fn: () => void) => () => {
      fn();
      close();
    };
    const commandRow = (c: Command): PanelRow => ({
      key: c.id,
      section: c.group,
      label: c.label,
      hint: c.hint,
      lead: c.toolIcon ?? ICONS[c.icon],
      // a command that opens a list in the line (`/views`, `/favorites`) fills the line and keeps it open
      run: c.fill
        ? () => focusBar(c.fill)
        : done(() => {
            c.run();
            record(`/${c.label}`, { command: c.id });
          }),
    });

    if (viewMode) {
      if (!parsed.text || !live || !caps.sentences) return out;
      if (didYou && didYou.text === parsed.text) {
        for (const o of didYou.pick.options)
          out.push({
            key: `pick:${o.slug}`,
            section: LINE_COPY.didYouMean(didYou.pick.name),
            label: o.title,
            hint: o.slug,
            lead: <Wand2 aria-hidden className="size-4" strokeWidth={1.6} />,
            run: () => runSentence(didYou.text, didYou.op, { ...didYou.chosen, [didYou.pick.name]: o.slug }),
          });
        return out;
      }
      out.push({
        key: "view-shape",
        section: "Actions",
        label: (
          <>
            {LINE_COPY.viewRow} <span className="text-muted-foreground">{parsed.text}</span>
          </>
        ),
        hint: parsed.op ? LINE_COPY.explainers[parsed.op] : undefined,
        lead: <Wand2 aria-hidden className="size-4" strokeWidth={1.6} />,
        run: () => {
          // the grammar reads the sentence into layers; text it cannot read is read by the model (useLlmLayers),
          // whose layers take the same route
          if (parsed.op === "remove") {
            const gone = useLayers.getState().apply("remove", parsed.text);
            useShellStore.getState().say(gone ? "Removed it from the view." : "No layer of the view matches that.");
            close();
            return;
          }
          if (useLayers.getState().preview && previewKey.current === `${parsed.op ?? "replace"}:${parsed.text}`) return commitPreview(parsed.text);
          runSentence(parsed.text, parsed.op ?? "replace", {});
        },
      });
      return out;
    }

    if (slash && intent && /^views(\s|$)/i.test(line.slice(1))) {
      // /views [words]: recent, then pinned, then the kit's ready views, each narrowed by the words; Enter replaces the
      // view, Shift+Enter adds to it. The last row is always the gallery.
      const words = line.slice(1).trim().replace(/^\S+\s*/, "").toLowerCase().split(/\s+/).filter(Boolean);
      const hit = (name: string) => words.every((w) => name.toLowerCase().includes(w));
      const seen = new Set<string>();
      const fresh = (name: string) => {
        const k = name.trim().toLowerCase();
        if (!k || seen.has(k) || !hit(name)) return false;
        seen.add(k);
        return true;
      };
      const VC = LINE_COPY.views;
      const apply = (name: string, layers: readonly Layer[], shift: boolean) => {
        const op = shift ? "stack" : "replace";
        if (applyLayers(op, layers)) {
          record(name, { stack: useLayers.getState().stack, lines: stackLines(layers) });
          useShellStore.getState().say(shift ? VC.added(name) : VC.applied(name));
        }
        close();
      };
      for (const s of [...(recentQ.data?.recent ?? [])].reverse()) {
        const savedLayers = specLayers({ v: 2, layers: (s.spec.stack as ViewStack | undefined)?.layers });
        if (!savedLayers || !fresh(s.text)) continue;
        out.push({ key: `views-recent:${s.at}:${s.text}`, section: VC.recent, label: s.text, lead: <History aria-hidden className="size-4" strokeWidth={1.6} />, run: (shift) => apply(s.text, savedLayers, shift) });
      }
      for (const v of viewsQ.data?.views ?? []) {
        if (!fresh(v.name)) continue;
        const layers = specLayers(v.spec);
        out.push({
          key: `views-pinned:${v.id}`,
          section: VC.pinned,
          label: v.name,
          lead: <Pin aria-hidden className="size-4" strokeWidth={1.6} />,
          // a pin from before layer stacks (V1) opens through the corner's own path, as one legacy layer
          run: (shift) => (layers ? apply(v.name, layers, shift) : done(() => runView(v))()),
        });
      }
      for (const r of ready) {
        if (!hit(r.name)) continue; // ready views are their own section: a recent step of the same name does not hide them
        out.push({
          key: `views-ready:${r.id}`,
          section: VC.ready,
          label: r.name,
          hint: r.layers ? r.description : VC.cannotRun,
          lead: <Layers aria-hidden className="size-4" strokeWidth={1.6} />,
          run: (shift) => {
            if (!r.layers) return useShellStore.getState().say(VC.cannotRunSay(r.name));
            // a view that needs one page takes the page in focus; with none (or several) the gallery asks for a name
            if (!isAnchored(r.layers)) return apply(r.name, r.layers, shift);
            const sel = [...useKb.getState().selection];
            if (sel.length === 1) return apply(`${r.name.replace(/\u2026$/, "").trim()} ${byId.get(sel[0]!)?.title || sel[0]}`, anchorLayers(r.layers, nodes, sel[0]!), shift);
            close();
            useGallery.getState().show();
          },
        });
      }
      out.push({
        key: "views-gallery",
        section: LINE_COPY.groups.views,
        label: VC.gallery,
        hint: VC.galleryHint,
        lead: <LayoutGrid aria-hidden className="size-4" strokeWidth={1.6} />,
        run: () => {
          close();
          useGallery.getState().show();
        },
      });
      return out;
    }

    if (slash && intent && /^fav/i.test(line.slice(1).trim())) {
      // /favorites [words]: the favorite pages as rows, Enter focuses one
      const rest = line.slice(1).trim().replace(/^\S+\s*/, "");
      out.push(
        ...favoriteRows(
          {
            colorBy,
            favorites: favs,
            focusNode: (id, shift) => {
              if (shift && useKb.getState().selection.size) useKb.getState().select(id);
              else onFocus(id);
              close();
            },
          },
          byId,
          rest,
        ),
      );
      return out;
    }
    if (slash) {
      const matches = filterCommands(commands, line.slice(1));
      for (const g of GROUP_ORDER) matches.filter((c) => c.group === g).forEach((c) => out.push(commandRow(c)));
      if (intent && !matches.length) {
        for (const c of closestCommands(commands, line.slice(1))) out.push({ ...commandRow(c), section: LINE_COPY.closestHeading });
        out.push({
          key: "search-instead",
          section: LINE_COPY.closestHeading,
          label: LINE_COPY.searchInstead(line.slice(1).trim()),
          lead: <Search aria-hidden className="size-4" strokeWidth={1.6} />,
          run: () => focusBar(line.slice(1).trim()),
        });
      }
      return out;
    }

    if (!text) {
      if (canUndo || (intent && layersUndo))
        out.push({
          key: "undo-shape",
          section: "Last shape",
          label: "Undo",
          hint: "Cmd-Z",
          lead: <Undo2 aria-hidden className="size-4" strokeWidth={1.6} />,
          run: done(undoShape),
        });
      const seen = new Set<string>();
      const recent = [...(recentQ.data?.recent ?? [])].reverse().filter((s) => (seen.has(s.text) ? false : (seen.add(s.text), true))).slice(0, RECENT_SHOWN);
      for (const s of recent) {
        out.push({
          key: `recent:${s.at}:${s.text}`,
          section: "Recent",
          label: s.text,
          hint: intent && Array.isArray(s.spec.lines) ? (s.spec.lines as string[]).join(" · ") : undefined,
          lead: <History aria-hidden className="size-4" strokeWidth={1.6} />,
          run: () => runRecent(s),
        });
      }
      for (const v of viewsQ.data?.views ?? []) {
        out.push({
          key: `view:${v.id}`,
          section: "Pinned views",
          label: v.name,
          lead: <Pin aria-hidden className="size-4" strokeWidth={1.6} />,
          run: done(() => runView(v)),
        });
      }
      return out;
    }

    const asksShape = looksLikeShape(text);
    const canShape = live && caps.shape;
    const shapeRow: PanelRow = {
      key: "shape",
      section: "Actions",
      label: (
        <>
          Shape the graph: <span className="text-muted-foreground">{text}</span>
        </>
      ),
      hint: shaping ? "working" : "this view only",
      lead: <Wand2 aria-hidden className="size-4" strokeWidth={1.6} />,
      // the panel stays open until the shape is drawn, so a refusal is read where the text was typed
      // (a new request replaces one still on its way: the older answer is dropped when it lands)
      run: () => {
        useShellStore.getState().setPendingOp(null);
        requestShape(text);
      },
    };
    const askRow: PanelRow | null = !caps.ask
      ? null
      : {
          key: "ask",
          section: "Actions",
          label: intent ? (
            <>
              {LINE_COPY.askRow} <span className="text-muted-foreground">"{text}"</span>
            </>
          ) : (
            <>
              Ask the agent: <span className="text-muted-foreground">{text}</span>
            </>
          ),
          hint: intent ? LINE_COPY.askHint : "opens the chat",
          lead: <MessageSquare aria-hidden className="size-4" strokeWidth={1.6} />,
          // flag graph-intent: the focus and the shown pages go with the question
          run: done(() => useChatDock.getState().ask(intent ? chatContextDraft(text) : text)),
        };
    if (intent && index) {
      // grouped, in a fixed order, each action row after them (./groupedRows)
      if (canShape && asksShape && /^match\b/i.test(text)) out.push(shapeRow);
      out.push(
        ...groupedRows({
          text,
          index,
          results,
          colorBy,
          views: viewsQ.data?.views ?? [],
          commands,
          commandRow,
          meaning,
          focusNode: (id, shift) => {
            if (shift && useKb.getState().selection.size) useKb.getState().select(id);
            else onFocus(id);
            close();
          },
          highlightSet: (ids) => {
            useKb.getState().setSelection(ids);
            close();
          },
          runView: (v) => {
            runView(v);
            close();
          },
          favorites: favs,
          textHits,
          byId,
          openChat: (id) => {
            close();
            void loadSession(defaultFetch, id).then(showDock);
          },
          openThink: (name) => {
            close();
            void router?.navigate({ to: "/think" as never, search: { note: name } as never });
          },
          openRaw: (path) => {
            close();
            useLayer.getState().openDrawer({ kind: "format", format: formatOfPath(path), path });
          },
        }),
      );
      if (canShape && asksShape && !/^match\b/i.test(text)) out.push(shapeRow);
      if (askRow) out.push(askRow);
      return out;
    }
    if (canShape && asksShape && /^match\b/i.test(text)) out.push(shapeRow);
    // a short list keeps the actions under it in view
    const shown = [...results.filter((r) => !r.related).slice(0, PAGES_SHOWN), ...results.filter((r) => r.related).slice(0, RELATED_SHOWN)];
    shown.forEach((r) => {
      out.push({
        key: `page:${r.node.id}:${r.related ? "r" : r.snippet ? "t" : "p"}`,
        section: r.related ? "Related ideas" : "Pages",
        label: r.node.title || r.node.id,
        detail: r.snippet,
        hint: r.node.type.replace(/-/g, " "),
        lead: <NodeSwatch type={r.node.type} color={swatchColor(r.node, colorBy)} className="size-3.5" />,
        run: (shift) => {
          if (shift) onRead(r.node.id);
          else onFocus(r.node.id);
          close();
        },
      });
    });
    if (text.length >= 2) {
      out.push({
        key: "mention",
        section: "Actions",
        label: (
          <>
            Show pages mentioning <span className="text-muted-foreground">{text}</span>
          </>
        ),
        hint: "+ neighbours",
        lead: <Search aria-hidden className="size-4" strokeWidth={1.6} />,
        run: done(() => {
          onShowMentions(text);
          record(`Pages mentioning ${text}`, { mention: text });
        }),
      });
    }
    if (canShape && asksShape && !/^match\b/i.test(text)) out.push(shapeRow);
    if (askRow) out.push(askRow);
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slash, viewMode, intent, index, line, text, commands, recentQ.data, viewsQ.data, results, colorBy, onFocus, onRead, onShowMentions, record, close, shaping, canUndo, layersUndo, undoShape, live, didYou, nodes, favs, byId, ready, focusBar, meaning, textHits, router]);

  /** A recent step: a command runs again; anything else goes back into the box to be edited or run. */
  function runRecent(s: RecentStep) {
    const saved = s.spec.stack as ViewStack | undefined;
    if (intent && saved && Array.isArray(saved.layers) && saved.layers.length) {
      // a recorded view stack goes back on as one undo step; its layers get fresh ids
      useLayers.getState().apply("replace", saved.layers.map((l) => ({ ...l, id: newLayerId() })));
      close();
      return;
    }
    const id = typeof s.spec.command === "string" ? s.spec.command : "";
    const cmd = id ? commands.find((c) => c.id === id) : undefined;
    if (cmd) {
      cmd.run();
      record(`/${cmd.label}`, { command: cmd.id });
      close();
    } else focusBar(s.text);
  }
  function runView(v: PinnedView) {
    useShellStore.getState().requestView(v);
  }

  // ---- flag graph-intent: the action menu on a row (the same NodeMenu as the node menu, with the action items)
  const actionCtx = useMemo<MenuContext>(() => {
    const showLayer = (ids: string[], text: string): Layer => makeLayer("show", "nodes", { nodes: [{ t: "name", slugs: ids }] }, text);
    const then = <A extends unknown[]>(fn: (...a: A) => void) => (...a: A) => {
      fn(...a);
      close();
    };
    return {
      openReader: then(onRead),
      openDetails: () => {},
      openPage: () => {},
      focus: then(onFocus),
      highlight: then((ids: string[]) => useKb.getState().setSelection(ids)),
      showOnly: then((ids: string[], label: string) => useLayers.getState().apply("replace", [showLayer(ids, ids.length === 1 ? `Only ${label}` : label)])),
      addToView: then((ids: string[], label: string) => useLayers.getState().apply("stack", [showLayer(ids, label)])),
      readSet: then((ids: string[]) => {
        if (ids[0]) useGraphUi.setState({ readerSlug: ids[0], readerSet: ids });
      }),
      // one layer per page, each printing as `show nodes within 1 hop of "<slug>"`
      expand: then((ids: string[]) =>
        useLayers.getState().apply("stack", ids.map((id) => makeLayer("show", "nodes", { nodes: [{ t: "hops", of: id, n: 1 }] }, LINE_COPY.neighborsOf(byId.get(id)?.title || id)))),
      ),
      colorSet: then((ids: string[], label: string) => useLayers.getState().apply("stack", [makeLayer("style", "nodes", { nodes: [{ t: "name", slugs: ids }] }, label, { style: { color: "type" } })])),
      chat: then((ids: string[]) => useChatDock.getState().ask(chatContextDraft("", ids))),
      think: then((ids: string[]) => openCaptureAbout(ids)),
      exportPages: then((ids: string[]) => void exportPages(ds, ids, { kbName, isShare: !caps.exportNotes, say: useShellStore.getState().say })),
    };
  }, [onRead, onFocus, byId, close, ds, kbName, caps.exportNotes]);
  const openMenu = useCallback((target: RowTarget, at: HTMLElement) => {
    const r = at.getBoundingClientRect();
    setMenu({ target, x: r.right - 24, y: r.bottom + 4 });
  }, []);
  useEffect(() => {
    if (!open) setMenu(null);
  }, [open]);
  /** Second Enter: apply what the canvas is showing, remember it in Recent and close like any apply. */
  function commitPreview(typed: string) {
    const lines = useLayers.getState().preview?.lines ?? [];
    setEditingLine(false);
    if (useLayers.getState().commitPreview()) record(typed, { stack: useLayers.getState().stack, lines });
    close();
  }
  /** The edited sentence applies exactly as written. */
  async function applyWritten(written: Layer[]) {
    const p = useLayers.getState().preview;
    let layers = written;
    if (needsMeaning(layers)) {
      const r = await useLayers.getState().resolveMeaning(layers, focusOne());
      if (!r.ok) return useShellStore.getState().setShapeError(LINE_COPY.focusOneFirst);
      layers = r.layers;
    }
    useLayers.getState().cancelPreview();
    setEditingLine(false);
    useLayers.getState().apply(p?.op ?? "replace", layers);
    record(layers.map((l) => l.text).join(" · "), { stack: useLayers.getState().stack, lines: layers.map((l) => l.text) });
    close();
  }
  /** The one focused page; none when nothing or several are focused. */
  function focusOne(): string | undefined {
    const sel = useKb.getState().selection;
    return sel.size === 1 ? [...sel][0] : undefined;
  }
  /** Read a `>` sentence into layers and apply them; a name left open asks, text the rules cannot read goes to the model. */
  function runSentence(typed: string, op: "replace" | "stack", chosen: Record<string, string>) {
    const focus = focusOne();
    settleSentence(planSentence(typed, nodes, { focus, chosen }), typed, op, { focus, chosen });
  }

  function settleSentence(plan: Plan, typed: string, op: "replace" | "stack", ctx: { focus?: string; chosen?: Record<string, string> }) {
    const say = useShellStore.getState().say;
    if (plan.kind === "ready") {
      setDidYou(null);
      // first Enter: show it on the canvas without applying; the second Enter (the same row) commits
      const key = `${op}:${typed}`;
      previewKey.current = key;
      if (!needsMeaning(plan.layers)) useLayers.getState().setPreview(op, plan.layers);
      else
        // `about` asks the meaning service first; a sentence typed over meanwhile drops this answer
        void useLayers
          .getState()
          .resolveMeaning(plan.layers, ctx.focus)
          .then((r) => {
            if (previewKey.current !== key || !intentRef.current || (openRef.current && parseMode(rawNow.current).text !== typed)) return;
            if (!r.ok) useShellStore.getState().setShapeError(LINE_COPY.focusOneFirst);
            else useLayers.getState().setPreview(op, r.layers);
          });
    } else if (plan.kind === "ask") setDidYou({ text: typed, op, pick: plan.pick, chosen: plan.chosen });
    else if (plan.kind === "missing") say(LINE_COPY.noSuchPage(plan.name));
    else llm.request(typed, op, ctx);
  }

  // a line typed in the overlay on another screen: take it over so the first Enter previews it here
  useEffect(() => {
    const line = useShellStore.getState().pendingLine;
    if (line === null) return;
    useShellStore.getState().clearLine();
    if (intentRef.current) focusBar(line);
  }, [focusBar]);
  /** Whether the highlighted row was chosen (arrow keys or pointer) rather than being the first row by default. */
  const picked = useRef(false);
  useEffect(() => {
    picked.current = false;
    setIdx(0);
  }, [raw]);
  useEffect(() => {
    if (!preview || !intent) return;
    if (previewKey.current !== `${parsed.op ?? "replace"}:${parsed.text}`) {
      useLayers.getState().cancelPreview();
      setEditingLine(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raw]);
  // closing the panel drops a preview nobody confirmed
  useEffect(() => {
    if (!open && useLayers.getState().preview) {
      useLayers.getState().cancelPreview();
      setEditingLine(false);
    }
  }, [open]);
  useEffect(() => () => useLayers.getState().cancelPreview(), []);
  // an error belongs to the text it answered: editing the text retires it
  useEffect(() => {
    useShellStore.getState().setShapeError(null);
  }, [raw]);
  useEffect(() => setIdx((i) => Math.min(i, Math.max(rows.length - 1, 0))), [rows.length]);

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      const n = rows.length;
      picked.current = true;
      if (n) setIdx((i) => (e.key === "ArrowDown" ? (i + 1) % n : (i - 1 + n) % n));
    } else if (e.key === "ArrowRight" && intent && open) {
      // the right arrow opens the highlighted row's menu once the caret is past the last letter
      const at = document.getElementById(optionId(idx));
      const t = e.currentTarget;
      const target = rows[idx]?.actions;
      if (target && at && t.selectionStart === t.value.length && t.selectionEnd === t.value.length) {
        e.preventDefault();
        openMenu(target, at);
      }
    } else if (e.key === "Enter") {
      if (e.nativeEvent.isComposing) return;
      e.preventDefault();
      setHintMode(null);
      // a bare `/views`: Enter shows the list; only a row picked by arrow keys (or the pointer) applies
      if (slash && intent && /^views\s*$/i.test(line.slice(1)) && !picked.current) return setOpen(true);
      rows[idx]?.run(e.shiftKey);
    } else if (e.key === "Tab" && intent && useLayers.getState().preview && !e.shiftKey) {
      e.preventDefault();
      setEditingLine(true);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setHintMode(null);
      if (intent && useLayers.getState().preview) {
        useLayers.getState().cancelPreview();
        return;
      }
      close();
    }
  };

  const status: PanelStatus | null = shaping
    ? { kind: "busy", text: "Shaping the graph" }
    : shapeError
      ? { kind: "error", text: shapeError }
      : shape && shapeCurrent
        ? { kind: "shape", text: pillText(shape.styleText, shape.pages) || "Shaped", skipped: shape.skipped }
        : null;

  const empty = viewMode ? LINE_COPY.viewEmpty : slash ? (intent ? (/^fav/i.test(line.slice(1).trim()) ? (favs.size ? "No favorite matches." : LINE_COPY.favorites.empty) : LINE_COPY.hints.command) : "No command matches.") : text ? "Nothing matches." : live && caps.ask ? "Type to search pages, / for commands, or ask a question." : "Type to search pages.";

  return (
    <div
      ref={box}
      className="pointer-events-auto absolute left-1/2 z-30 -translate-x-1/2 transition-[width] duration-200 motion-reduce:transition-none"
      style={{ top, width: open ? "min(640px, calc(100% - 9rem))" : "min(520px, calc(100% - 9rem))" }}
      data-testid="graph-shell"
      onBlur={(e) => {
        const to = e.relatedTarget as HTMLElement | null;
        if (!e.currentTarget.contains(to) && !to?.closest?.("[role=menu]")) setOpen(false);
      }}
    >
      <SearchBar
        value={raw}
        onChange={(v) => {
          setRaw(v);
          setOpen(true);
        }}
        open={open}
        onOpen={openPanel}
        onKeyDown={onKeyDown}
        activeId={rows.length ? optionId(idx) : undefined}
        inputRef={input}
        placeholder={intent ? (caps.sentences ? LINE_COPY.placeholder : LINE_COPY.placeholderShare) : `Search ${kbName}`}
        notice={open ? undefined : notice?.text}
      />
      {intent && <Chips byId={byId} />}
      {intent && open && viewMode && <ResolvedLine lines={preview?.lines ?? null} count={preview?.count ?? 0} editing={editingLine} onEditing={setEditingLine} onApply={applyWritten} />}
      {open && <SearchPanel rows={rows} idx={idx} onHover={(i) => {
          picked.current = true;
          setIdx(i);
        }} empty={empty} status={status} hint={sentenceBlocked ? LINE_COPY.sentenceUnavailable : hintMode ? LINE_COPY.hints[hintMode] : undefined} views={!text && !slash && viewChoices.length ? viewChoices : undefined} onMenu={intent ? (i, at) => rows[i]?.actions && openMenu(rows[i]!.actions!, at) : undefined} />}
      {menu &&
        createPortal(
          <NodeMenu
            node={menu.target.kind === "node" ? menu.target.node : ({ id: "set", title: menu.target.label, type: "set" } as GNode)}
            title={menu.target.kind === "set" ? menu.target.label : undefined}
            x={menu.x}
            y={menu.y}
            colorBy={colorBy}
            ctx={actionCtx}
            items={menu.target.kind === "node" ? ACTION_ITEMS : setActionItems(menu.target.ids, menu.target.label)}
            onClose={() => {
              setMenu(null);
              input.current?.focus({ preventScroll: true });
            }}
          />,
          document.body,
        )}
      {intent && (
        <Gallery
          nodes={nodes}
          ready={ready}
          pinned={viewsQ.data?.views ?? []}
          recent={recentQ.data?.recent ?? []}
          onRecord={(label, layers) => record(label, { stack: useLayers.getState().stack, lines: stackLines(layers) })}
          onLegacy={(v) => runView(v as Parameters<typeof runView>[0])}
        />
      )}
    </div>
  );
}
