import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowRightLeft,
  CircleHelp,
  CornerDownRight,
  Feather,
  History,
  ListFilter,
  Maximize,
  MessageSquare,
  Network,
  Pin,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Wand2,
  Wind,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useDataSource, type PinnedView, type RecentStep } from "@/api";
import { useFlag } from "@/flags/useFlag";
import { useApiQuery } from "@/lib/useApiQuery";
import { IS_SHARE } from "@/share/env";
import { NodeSwatch } from "../encoding/NodeMarkSvg";
import { useToolHost } from "../hostContext";
import { colorOf, effectiveColorBy, type ColorBy } from "../style";
import { useChatDock } from "../tools/chatDockStore";
import { useVisibleTools } from "../tools";
import type { GNode } from "../types";
import { buildCommands, filterCommands, GROUP_ORDER, type Command, type CommandIcon } from "./commands";
import { SearchBar } from "./SearchBar";
import { optionId, SearchPanel, type PanelRow } from "./SearchPanel";
import { looksLikeShape, requestShape, useShellStore } from "./shellStore";
import { usePageResults } from "./usePageResults";

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
};

const NOTICE_MS = 3200;
const RECENT_SHOWN = 5;
const PAGES_SHOWN = 6;
const RELATED_SHOWN = 3;

interface Props {
  nodes: readonly GNode[];
  byId: ReadonlyMap<string, GNode>;
  colorBy: ColorBy;
  /** Enter on a page: centre on it (bringing it in when it is filtered out). */
  onFocus: (id: string) => void;
  /** Shift+Enter on a page: read it in the side reader. */
  onRead: (id: string) => void;
  /** "Show pages mentioning ...". */
  onShowMentions: (q: string) => void;
  onFit: () => void;
  onZoom: (factor: number) => void;
  onReheat: () => void;
  onRefresh: () => void;
  /** Merge params into the URL (the `kbs` param). */
  setParams?: (patch: Record<string, string | undefined>) => void;
}

/**
 * The calm shell of the graph (flag graph-shell): the search panel is the one command surface. A bar at top
 * centre unfolds, on focus or Cmd/Ctrl+K, into recent steps and pinned views at rest, live page results while
 * typing, commands after a slash, and two free-text rows (ask the agent, shape the graph).
 */
export function GraphShell({ nodes, byId, colorBy, onFocus, onRead, onShowMentions, onFit, onZoom, onReheat, onRefresh, setParams }: Props) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const host = useToolHost();
  const tools = useVisibleTools();
  const kbViewOn = useFlag("kb-view") && ds.kind !== "embedded";
  const [raw, setRaw] = useState("");
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const notice = useShellStore((s) => s.notice);

  const text = raw.trim();
  const slash = raw.startsWith("/");

  // ---- data: recent steps and pinned views (rest), the knowledge bases (kb-view), page results (typing)
  const live = ds.kind !== "embedded";
  const recentQ = useApiQuery(["recent"], (d) => d.listRecent(), { enabled: live, retry: false, staleTime: 5_000 });
  const viewsQ = useApiQuery(["views"], (d) => d.listViews(), { enabled: live, retry: false, staleTime: 5_000 });
  const kbQ = useApiQuery(["kb"], (d) => d.getKb(), { staleTime: Infinity, retry: false });
  const kbListQ = useApiQuery(["kb-list"], (d) => d.listKbs(), { enabled: kbViewOn, staleTime: 30_000 });
  const results = usePageResults(nodes, byId, raw, !slash && text.length > 0);
  const kbName = kbQ.data?.name ?? "Knowledge Base";

  const record = useCallback(
    (label: string, spec: Record<string, unknown>) => {
      if (!live) return;
      // re-running the same step must not fill the server's short history with copies
      const newest = recentQ.data?.recent.at(-1);
      if (newest && newest.text === label) return;
      ds.addRecent(label, spec).then((r) => qc.setQueryData(["recent"], r), () => {});
    },
    [ds, qc, live, recentQ.data],
  );

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
        share: IS_SHARE,
      }),
    [onFit, onZoom, onReheat, onRefresh, tools, host, setParams, kbViewOn, kbListQ.data],
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
  }, [focusBar]);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) close(false);
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
      run: done(() => {
        c.run();
        record(`/${c.label}`, { command: c.id });
      }),
    });

    if (slash) {
      for (const g of GROUP_ORDER) filterCommands(commands, raw.slice(1)).filter((c) => c.group === g).forEach((c) => out.push(commandRow(c)));
      return out;
    }

    if (!text) {
      const seen = new Set<string>();
      const recent = [...(recentQ.data?.recent ?? [])].reverse().filter((s) => (seen.has(s.text) ? false : (seen.add(s.text), true))).slice(0, RECENT_SHOWN);
      for (const s of recent) {
        out.push({
          key: `recent:${s.at}:${s.text}`,
          section: "Recent",
          label: s.text,
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

    const shape = looksLikeShape(text);
    const shapeRow: PanelRow = {
      key: "shape",
      section: "Actions",
      label: (
        <>
          Shape the graph: <span className="text-muted-foreground">{text}</span>
        </>
      ),
      hint: "coming soon",
      lead: <Wand2 aria-hidden className="size-4" strokeWidth={1.6} />,
      run: done(() => {
        record(text, { text });
        requestShape(text);
        useShellStore.getState().say("Shaping the graph from text is coming soon.");
      }),
    };
    if (shape && /^match\b/i.test(text)) out.push(shapeRow);
    const colour = effectiveColorBy(colorBy);
    // a short list keeps the actions under it in view
    const shown = [...results.filter((r) => !r.related).slice(0, PAGES_SHOWN), ...results.filter((r) => r.related).slice(0, RELATED_SHOWN)];
    shown.forEach((r) => {
      out.push({
        key: `page:${r.node.id}:${r.related ? "r" : r.snippet ? "t" : "p"}`,
        section: r.related ? "Related ideas" : "Pages",
        label: r.node.title || r.node.id,
        detail: r.snippet,
        hint: r.node.type.replace(/-/g, " "),
        lead: <NodeSwatch type={r.node.type} color={colorOf(r.node, colour)} className="size-3.5" />,
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
    if (shape && !/^match\b/i.test(text)) out.push(shapeRow);
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
        run: done(() => useChatDock.getState().ask(text)),
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slash, raw, text, commands, recentQ.data, viewsQ.data, results, colorBy, onFocus, onRead, onShowMentions, record, close]);

  /** A recent step: a command runs again; anything else goes back into the box to be edited or run. */
  function runRecent(s: RecentStep) {
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
    useShellStore.getState().say("Opening a pinned view is coming soon.");
  }

  useEffect(() => setIdx(0), [raw]);
  useEffect(() => setIdx((i) => Math.min(i, Math.max(rows.length - 1, 0))), [rows.length]);

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      const n = rows.length;
      if (n) setIdx((i) => (e.key === "ArrowDown" ? (i + 1) % n : (i - 1 + n) % n));
    } else if (e.key === "Enter") {
      if (e.nativeEvent.isComposing) return;
      e.preventDefault();
      rows[idx]?.run(e.shiftKey);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  };

  const empty = slash ? "No command matches." : text ? "Nothing matches." : live && !IS_SHARE ? "Type to search pages, / for commands, or ask a question." : "Type to search pages.";

  return (
    <div
      ref={box}
      className="pointer-events-auto absolute left-1/2 top-[13px] z-30 -translate-x-1/2 transition-[width] duration-200 motion-reduce:transition-none"
      style={{ width: open ? "min(640px, calc(100% - 9rem))" : "min(520px, calc(100% - 9rem))" }}
      data-testid="graph-shell"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
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
        kbName={kbName}
        notice={open ? undefined : notice?.text}
        onKbClick={() => focusBar("/knowledge")}
      />
      {open && <SearchPanel rows={rows} idx={idx} onHover={setIdx} empty={empty} />}
    </div>
  );
}
