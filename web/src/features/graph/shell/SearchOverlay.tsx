import { useNavigate } from "@tanstack/react-router";
import { CornerDownRight, Feather, MessageSquare, Pin, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useDataSource, type PinnedView } from "@/api";
import { flag } from "@/flags";
import { useFlag } from "@/flags/useFlag";
import { useKb } from "@/lib/store";
import { useApiQuery } from "@/lib/useApiQuery";
import { IS_SHARE } from "@/share/env";
import type { ToolHost } from "../hostContext";
import { openCaptureAbout } from "../captureAbout";
import { ACTION_ITEMS, type MenuContext } from "../menu";
import { NodeMenu } from "../NodeMenu";
import { goCommands, filterCommands, type Command } from "./commands";
import { LINE_COPY } from "./copy";
import { groupedRows } from "./groupedRows";
import { SearchLine } from "./SearchLine";
import type { PanelRow } from "./SearchPanel";
import { buildSearchIndex, withNames, type RowTarget } from "./searchGroups";
import { isThink } from "./searchGroups";
import { parseMode, useShellStore } from "./shellStore";
import { usePageResults } from "./usePageResults";
import { askAbout, useChatDock } from "../tools/chatDockStore";
import type { GNode } from "../types";
import { useUi } from "@/app/ui-store";

const O = LINE_COPY.overlay;
/** The menu entries that make sense off the graph (the others change the graph's view and need it on screen). */
const OVERLAY_ACTIONS = new Set(["focus", "read", "favorite", "chat", "think", "export"]);

const isTyping = (t: EventTarget | null) => t instanceof HTMLElement && !!t.closest("input, textarea, select, [contenteditable]");

/**
 * The search line as a sheet on every screen (flag graph-intent): Cmd/Ctrl+K opens it, Escape closes it and focus
 * returns to where it was. On the graph the shell's own line takes the key, so this stays out of the way there.
 */
export function SearchOverlay() {
  const on = useFlag("graph-intent");
  const open = useUi((s) => s.lineOpen);
  const setOpen = useUi((s) => s.setLineOpen);

  useEffect(() => {
    if (!on) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.key.toLowerCase() !== "k") return;
      // the graph's own line is on screen: it owns the key
      if (document.querySelector('[data-testid="graph-shell"]')) return;
      const inLine = e.target instanceof HTMLElement && !!e.target.closest("[data-testid=search-overlay]");
      if (isTyping(e.target) && !inLine) return;
      e.preventDefault();
      e.stopPropagation();
      setOpen(!useUi.getState().lineOpen);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [on, setOpen]);

  if (!on || !open) return null;
  return <Sheet onClose={() => setOpen(false)} />;
}

function Sheet({ onClose }: { onClose: () => void }) {
  const ds = useDataSource();
  const navigate = useNavigate();
  const [raw, setRaw] = useState("");
  const [idx, setIdx] = useState(0);
  const [menu, setMenu] = useState<{ target: RowTarget; x: number; y: number } | null>(null);
  const input = useRef<HTMLInputElement>(null);

  // focus returns to where it was when the sheet goes away
  useEffect(() => {
    const was = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    input.current?.focus();
    return () => was?.focus?.({ preventScroll: true });
  }, []);

  const go = useCallback((to: string, search?: Record<string, string>) => void navigate({ to: to as "/", ...(search ? { search: search as never } : {}) }), [navigate]);
  const host = useMemo<ToolHost>(() => ({ go: (to, search) => (onClose(), go(to, search)), href: (to) => to, openPage: (slug) => (onClose(), go(`/pages/${encodeURIComponent(slug)}`)) }), [go, onClose]);

  const live = ds.kind !== "embedded";
  const graphQ = useApiQuery(["graph", false], (d) => d.getGraph());
  const viewsQ = useApiQuery(["views"], (d) => d.listViews(), { enabled: live, retry: false, staleTime: 5_000 });
  const nodes = useMemo<GNode[]>(() => graphQ.data?.nodes ?? [], [graphQ.data]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n] as const)), [nodes]);
  const parsed = parseMode(raw);
  const text = raw.trim();
  const slash = raw.startsWith("/");
  const viewMode = parsed.mode === "view";
  const results = usePageResults(nodes, byId, raw, !slash && !viewMode && text.length > 0);

  const commands = useMemo<Command[]>(
    () => [
      { id: "open-graph", label: O.openGraph, group: "Go to", icon: "go", hint: O.openGraphHint, run: () => host.go("/graph") },
      ...goCommands(host, IS_SHARE),
    ],
    [host],
  );
  const index = useMemo(() => withNames(buildSearchIndex(nodes), viewsQ.data?.views ?? [], commands.map((c) => ({ id: c.id, label: c.label }))), [nodes, viewsQ.data, commands]);

  const openNode = useCallback(
    (n: GNode) => {
      onClose();
      if (isThink(n) && flag("screen.think")) go("/think", { note: n.id.endsWith(".md") ? n.id : `${n.id}.md` });
      else go(`/pages/${encodeURIComponent(n.slug ?? n.id)}`);
    },
    [go, onClose],
  );
  const onGraph = useCallback(
    (id: string) => {
      onClose();
      go("/graph", { select: id, focus: id });
    },
    [go, onClose],
  );
  const showView = useCallback(
    (v: PinnedView) => {
      onClose();
      go("/graph");
      useShellStore.getState().requestView(v);
    },
    [go, onClose],
  );

  const rows = useMemo<PanelRow[]>(() => {
    const lead = (c: Command) => (c.icon === "think" ? <Feather aria-hidden className="size-4" strokeWidth={1.6} /> : <CornerDownRight aria-hidden className="size-4" strokeWidth={1.6} />);
    const commandRow = (c: Command): PanelRow => ({
      key: c.id,
      section: c.group,
      label: c.label,
      hint: c.hint,
      lead: lead(c),
      run: () => {
        onClose();
        c.run();
      },
    });
    if (viewMode) {
      // the sentence is read and previewed on the graph: hand it over and go there
      if (!parsed.text || !live || IS_SHARE) return [];
      return [
        {
          key: "view-handoff",
          section: "Actions",
          label: (
            <>
              {O.handOff} <span className="text-muted-foreground">{parsed.text}</span>
            </>
          ),
          hint: O.handOffHint,
          lead: <Wand2 aria-hidden className="size-4" strokeWidth={1.6} />,
          run: () => {
            onClose();
            useShellStore.getState().requestLine(raw);
            go("/graph");
          },
        },
      ];
    }
    if (slash) return filterCommands(commands, raw.slice(1)).map(commandRow);
    if (!text) {
      return (viewsQ.data?.views ?? []).map<PanelRow>((v) => ({
        key: `view:${v.id}`,
        section: "Pinned views",
        label: v.name,
        lead: <Pin aria-hidden className="size-4" strokeWidth={1.6} />,
        run: () => showView(v),
      }));
    }
    const out = groupedRows({
      text,
      index,
      results,
      colorBy: "type",
      views: viewsQ.data?.views ?? [],
      commands,
      commandRow,
      focusNode: (id, shift) => {
        const n = byId.get(id);
        if (shift || !n) onGraph(id);
        else openNode(n);
      },
      highlightSet: (ids) => {
        useKb.getState().setSelection(ids);
        onClose();
        go("/graph");
      },
      runView: showView,
    });
    if (!IS_SHARE) {
      out.push({
        key: "ask",
        section: "Actions",
        label: (
          <>
            Ask the agent: <span className="text-muted-foreground">{text}</span>
          </>
        ),
        hint: "opens the chat",
        lead: <MessageSquare aria-hidden className="size-4" strokeWidth={1.6} />,
        run: () => {
          onClose();
          go("/graph");
          useChatDock.getState().ask(text);
        },
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, slash, raw, text, parsed.text, live, commands, index, results, viewsQ.data, byId, openNode, onGraph, showView, go, onClose]);

  useEffect(() => setIdx(0), [raw]);
  useEffect(() => setIdx((i) => Math.min(i, Math.max(rows.length - 1, 0))), [rows.length]);

  const actionCtx = useMemo<MenuContext>(() => {
    const then = <A extends unknown[]>(fn: (...a: A) => void) => (...a: A) => {
      fn(...a);
      setMenu(null);
      onClose();
    };
    return {
      openReader: then((id: string) => { const n = byId.get(id); if (n) openNode(n); }),
      openDetails: () => {},
      openPage: () => {},
      focus: then((id: string) => onGraph(id)),
      highlight: then((ids: string[]) => { useKb.getState().setSelection(ids); go("/graph"); }),
      chat: then((ids: string[]) => { go("/graph"); useChatDock.getState().ask(askAbout(ids.map((id) => ({ id })))); }),
      think: then((ids: string[]) => openCaptureAbout(ids)),
    };
  }, [byId, openNode, onGraph, go, onClose]);
  const items = useMemo(() => ACTION_ITEMS.filter((i) => OVERLAY_ACTIONS.has(i.id)), []);
  const openMenu = useCallback((i: number, at: HTMLElement) => {
    const target = rows[i]?.actions;
    if (!target) return;
    const r = at.getBoundingClientRect();
    setMenu({ target, x: r.right - 24, y: r.bottom + 4 });
  }, [rows]);

  const empty = viewMode ? LINE_COPY.viewEmpty : slash ? LINE_COPY.hints.command : text ? "Nothing matches." : live && !IS_SHARE ? O.empty : O.emptyShare;

  return (
    <div
      data-testid="search-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={O.label}
      className="fixed inset-0 z-50 flex items-start justify-center bg-foreground/20 px-4 pt-[14vh]"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-[640px]">
        <SearchLine
          context="overlay"
          value={raw}
          onChange={setRaw}
          rows={rows}
          idx={idx}
          setIdx={setIdx}
          placeholder={LINE_COPY.placeholder}
          empty={empty}
          inputRef={input}
          onClose={onClose}
          onMenu={openMenu}
        />
      </div>
      {menu &&
        createPortal(
          <NodeMenu
            node={menu.target.kind === "node" ? menu.target.node : ({ id: "set", title: menu.target.label, type: "set" } as GNode)}
            title={menu.target.kind === "set" ? menu.target.label : undefined}
            x={menu.x}
            y={menu.y}
            colorBy="type"
            ctx={actionCtx}
            items={menu.target.kind === "node" ? items : [{ id: "highlight", label: LINE_COPY.actions.highlight.label, hint: LINE_COPY.actions.highlight.hint, run: (_n, c) => c.highlight?.(menu.target.kind === "set" ? menu.target.ids : []) }]}
            onClose={() => {
              setMenu(null);
              input.current?.focus({ preventScroll: true });
            }}
          />,
          document.body,
        )}
    </div>
  );
}
