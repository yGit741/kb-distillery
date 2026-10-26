import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { SearchHit } from "@/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { findPages, textHits } from "./pageSearch";
import { NodeSwatch } from "./encoding/NodeMarkSvg";
import { colorOf, effectiveColorBy, type ColorBy } from "./style";
import type { GNode } from "./types";
import { useChatDock } from "./tools/chatDockStore";

export const FINDER_ID = "graph-finder";

type Item =
  | { kind: "page"; node: GNode; snippet?: string }
  | { kind: "show"; label: string }
  | { kind: "mention"; q: string }
  | { kind: "agent"; question: string };

interface Props {
  nodes: readonly GNode[];
  byId: ReadonlyMap<string, GNode>;
  colorBy: ColorBy;
  visible: ReadonlySet<string>;
  /** Enter: centre on the page (bringing it in if filtered out). */
  onFocus: (id: string) => void;
  /** Shift+Enter: read it in the side reader. */
  onRead: (id: string) => void;
  /** Show these pages and their neighbours as a view. */
  onShowPicked: (ids: string[]) => void;
  /** Show every page that mentions the query. */
  onShowMentions: (q: string) => void;
  /** Where the box sits: floating over the canvas (default) or filling the app header's slot. */
  placement?: "canvas" | "header";
}

/**
 * Space search: title and slug matches, full-text hits, "pages mentioning …", and a pick list (Tab) that is
 * shown all at once with its neighbours. "/" sends the rest of the line to the chat dock.
 */
export function Finder({ nodes, byId, colorBy, visible, onFocus, onRead, onShowPicked, onShowMentions, placement = "canvas" }: Props) {
  const [raw, setRaw] = useState("");
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [debounced, setDebounced] = useState("");
  const [picked, setPicked] = useState<Map<string, GNode>>(new Map());
  const [agentNote, setAgentNote] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const q = raw.trim().toLowerCase();
  const agent = raw.startsWith("/");

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q), 150);
    return () => window.clearTimeout(t);
  }, [q]);

  const text = useApiQuery<{ hits: SearchHit[] }>(["graph-text", debounced], (ds) => ds.search(debounced, 12), {
    enabled: !agent && debounced.length >= 2,
    staleTime: 60_000,
  });

  const pages = useMemo(() => (agent ? [] : findPages(nodes, q)), [nodes, q, agent]);
  const texts = useMemo(
    () => (agent || debounced !== q ? [] : textHits(text.data?.hits ?? [], byId, pages)),
    [text.data, byId, pages, agent, debounced, q],
  );

  const items = useMemo<Item[]>(() => {
    if (agent) return [{ kind: "agent", question: raw.slice(1).trim() }];
    const out: Item[] = [];
    if (picked.size) out.push({ kind: "show", label: `Show ${picked.size} picked page${picked.size === 1 ? "" : "s"}` });
    pages.forEach((node) => out.push({ kind: "page", node }));
    texts.forEach((h) => {
      const node = byId.get(h.id);
      if (node) out.push({ kind: "page", node, snippet: h.snippet });
    });
    if (q.length >= 2) out.push({ kind: "mention", q: raw.trim() });
    return out;
  }, [agent, raw, picked, pages, texts, byId, q]);

  useEffect(() => setIdx(picked.size && !q ? 0 : picked.size ? 1 : 0), [items.length, picked.size, q]);

  const close = (blur = true) => {
    setOpen(false);
    if (blur) {
      setRaw("");
      input.current?.blur();
    }
  };

  const togglePick = (n: GNode) => {
    setPicked((m) => {
      const next = new Map(m);
      if (!next.delete(n.id)) next.set(n.id, n);
      return next;
    });
    setRaw("");
    input.current?.focus();
  };

  const run = (it: Item | undefined, shift: boolean) => {
    if (!it) return;
    if (it.kind === "agent") {
      if (!it.question) return setAgentNote("Type a question after the slash.");
      useChatDock.getState().ask(it.question);
      close();
      return;
    }
    if (it.kind === "mention") {
      onShowMentions(it.q);
    } else if (it.kind === "show") {
      onShowPicked([...picked.keys()]);
      setPicked(new Map());
    } else if (shift) {
      onRead(it.node.id);
    } else if (picked.size) {
      onShowPicked([...picked.keys(), it.node.id]);
      setPicked(new Map());
    } else {
      onFocus(it.node.id);
    }
    close();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIdx((i) => (items.length ? (i + 1) % items.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIdx((i) => (items.length ? (i - 1 + items.length) % items.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(items[idx], e.shiftKey);
    } else if (e.key === "Tab") {
      const it = items[idx];
      if (it?.kind === "page") {
        e.preventDefault();
        togglePick(it.node);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  };

  const listId = "graph-finder-list";
  const showList = open && (items.length > 0 || !!q || picked.size > 0);
  return (
    <div
      className={cn(
        "pointer-events-auto",
        // on the canvas (the embed has no header) it sits under the views bar, not on it
        placement === "header" ? "relative mx-auto w-full max-w-md" : "absolute left-1/2 top-14 z-20 w-[min(28rem,calc(100%-8rem))] -translate-x-1/2",
      )}
    >
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
        <input
          ref={input}
          id={FINDER_ID}
          data-tour="graph-search"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-label="Search a page (Space)"
          type="search"
          autoComplete="off"
          spellCheck={false}
          placeholder="Search anything"
          className="h-9 w-full rounded-lg border bg-card/95 pl-8 pr-3 text-sm shadow-[var(--shadow)] placeholder:text-muted-foreground"
          value={raw}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onChange={(e) => {
            setRaw(e.target.value);
            setOpen(true);
            setAgentNote("");
          }}
          onKeyDown={onKey}
        />
      </div>
      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Results"
          className={cn(
            "mt-1 max-h-[60vh] overflow-y-auto rounded-lg border bg-popover p-1 text-sm shadow-[var(--shadow)]",
            placement === "header" && "absolute left-0 right-0 z-50",
          )}
          onMouseDown={(e) => e.preventDefault()}
        >
          {picked.size > 0 && (
            <li className="flex flex-wrap gap-1 px-1 pb-1" aria-label="Picked pages">
              {[...picked.values()].map((n) => (
                <span key={n.id} className="flex items-center gap-1 rounded-md bg-accent-soft px-1.5 py-0.5 text-xs">
                  <NodeSwatch type={n.type} color={colorOf(n, effectiveColorBy(colorBy))} className="size-3" />
                  <span className="max-w-40 truncate">{n.title || n.id}</span>
                  <button type="button" aria-label={`Unpick ${n.title || n.id}`} onClick={() => togglePick(n)}>
                    ×
                  </button>
                </span>
              ))}
            </li>
          )}
          {items.map((it, i) => (
            <li
              key={it.kind === "page" ? `${it.node.id}:${it.snippet ? "t" : "p"}` : it.kind}
              role="option"
              aria-selected={i === idx}
              className={cn("flex cursor-pointer items-start gap-2 rounded px-2 py-1.5", i === idx && "bg-accent")}
              onMouseEnter={() => setIdx(i)}
              onClick={(e) => run(it, e.shiftKey)}
            >
              {it.kind === "page" ? (
                <>
                  <button
                    type="button"
                    tabIndex={-1}
                    aria-label={picked.has(it.node.id) ? "Unpick" : "Pick (Tab)"}
                    className={cn("mt-0.5 size-4 shrink-0 rounded border text-[10px] leading-none", picked.has(it.node.id) && "bg-primary text-primary-foreground")}
                    onClick={(e) => {
                      e.stopPropagation();
                      togglePick(it.node);
                    }}
                  >
                    {picked.has(it.node.id) ? "✓" : ""}
                  </button>
                  <NodeSwatch type={it.node.type} color={colorOf(it.node, effectiveColorBy(colorBy))} className="mt-1 size-3" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{it.node.title || it.node.id}</span>
                    {it.snippet && <span className="block truncate text-xs text-muted-foreground">{it.snippet}</span>}
                  </span>
                  {!visible.has(it.node.id) && <small className="text-muted-foreground" title="Not in the current view: showing it brings it in">hidden</small>}
                  <small className="text-muted-foreground">{it.node.type.replace(/-/g, " ")}</small>
                </>
              ) : it.kind === "show" ? (
                <span className="flex-1 font-medium">{it.label} <small className="font-normal text-muted-foreground">↵ + neighbours</small></span>
              ) : it.kind === "mention" ? (
                <span className="flex-1">
                  Show pages mentioning “{it.q}” <small className="text-muted-foreground">+ neighbours</small>
                </span>
              ) : (
                <span className="flex-1">
                  {it.question ? `Ask: “${it.question}”` : "Type a question after the slash…"}{" "}
                  <small className="text-muted-foreground">opens the chat</small>
                  {agentNote && <span className="mt-1 block text-xs text-muted-foreground">{agentNote}</span>}
                </span>
              )}
            </li>
          ))}
          {!items.length && <li className="px-2 py-2 text-muted-foreground">Nothing matches.</li>}
        </ul>
      )}
    </div>
  );
}
