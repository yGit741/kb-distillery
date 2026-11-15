import { create } from "zustand";
import { flag } from "@/flags";
import { useKb } from "@/lib/store";
import type { SimLink } from "./types";

/**
 * Flag edge-select: edges you can light up and keep, in every view. Hovering an edge lights it (./citeHover draws it),
 * a click keeps it, Cmd- or Shift-click adds or removes it. A kept edge brings its two pages into the page selection
 * (`useKb().selection`), so every selection tool acts on them; taking it out takes back only the pages it brought.
 */

type End = SimLink["source"];
const idOf = (e: End): string => (typeof e === "object" ? e.id : e);

/** An edge's two page ids, source first. */
export const endsOf = (l: Pick<SimLink, "source" | "target">): [string, string] => [idOf(l.source), idOf(l.target)];

/** One key per drawn edge: its kind and both ends. Stable across new data, where the link objects are new. */
export const edgeKey = (l: Pick<SimLink, "source" | "target" | "kind">): string => {
  const [a, b] = endsOf(l);
  return `${l.kind}|${a}|${b}`;
};

/** Real links between pages; the data layer's pile connectors are not edges you select. */
export const selectable = (l: Pick<SimLink, "kind">): boolean => l.kind !== "pile-page" && l.kind !== "pile-pile";

/**
 * The edges that light up under the pointer: every drawn edge of a kind that is not hidden (flag edge-select), else
 * the citations only (Citations by meaning, where this began).
 */
export function lightable(l: Pick<SimLink, "kind">, hidden: ReadonlySet<string>, on: boolean = flag("edge-select")): boolean {
  return on ? selectable(l) && !hidden.has(l.kind) : l.kind === "cites";
}

const human = (s: string) => s.replace(/[_-]+/g, " ").trim();

/** The words written on a lit edge: what the link says, read from its source to its target. */
export function edgeWord(l: Pick<SimLink, "kind" | "shared" | "rel">): string {
  switch (l.kind) {
    case "cites":
      return "cites";
    case "wikilink":
      return "links to";
    case "book":
      return "part of";
    case "shared": {
      const n = l.shared ?? 1;
      return `${n} shared source${n === 1 ? "" : "s"}`;
    }
    case "related":
      return l.rel ? human(l.rel) : "related to";
    default:
      return human(l.kind);
  }
}

/** Every kind reads one way, with an arrow at its target, except shared sources, which join two pages both ways. */
export const directed = (l: Pick<SimLink, "kind">): boolean => l.kind !== "shared";

type Ends = readonly [string, string];

interface EdgeSelectState {
  /** the kept edges by key, with their two pages */
  edges: ReadonlyMap<string, Ends>;
  /** the pages kept edges brought into the selection: taking an edge out takes back only these */
  brought: ReadonlySet<string>;
  /** how many kept edges the canvas draws now (a view without that link, or with its kind hidden, draws fewer) */
  shown: number;
  setShown: (n: number) => void;
  /** A plain click: this edge alone, and its two pages the whole selection. */
  keep: (l: Pick<SimLink, "source" | "target" | "kind">) => void;
  /** Cmd- or Shift-click: add the edge (and its pages), or take it out (and the pages only it brought). */
  toggle: (l: Pick<SimLink, "source" | "target" | "kind">) => void;
  clear: () => void;
}

const NONE: ReadonlyMap<string, Ends> = new Map();
const NO_PAGES: ReadonlySet<string> = new Set();

export const useEdgeSelect = create<EdgeSelectState>((set, get) => ({
  edges: NONE,
  brought: NO_PAGES,
  shown: 0,
  setShown: (n) => {
    if (get().shown !== n) set({ shown: n });
  },
  keep: (l) => {
    const ends = endsOf(l);
    // the edges first: the page selection that follows already holds both ends, so the edge stays (see the sync below)
    set({ edges: new Map([[edgeKey(l), ends]]), brought: new Set(ends) });
    useKb.getState().setSelection(ends);
  },
  toggle: (l) => {
    const key = edgeKey(l);
    const { edges, brought } = get();
    const sel = useKb.getState().selection;
    if (edges.has(key)) {
      const rest = new Map(edges);
      rest.delete(key);
      const still = new Set([...rest.values()].flat());
      const back = endsOf(l).filter((id) => brought.has(id) && !still.has(id));
      set({ edges: rest, brought: new Set([...brought].filter((id) => !back.includes(id))) });
      if (back.length) useKb.getState().setSelection([...sel].filter((id) => !back.includes(id)));
      return;
    }
    const ends = endsOf(l);
    const added = ends.filter((id) => !sel.has(id));
    set({ edges: new Map(edges).set(key, ends), brought: new Set([...brought, ...added]) });
    // one change of the page selection, holding both ends at once, so the sync never sees the edge half selected
    if (added.length) useKb.getState().setSelection([...sel, ...added]);
  },
  clear: () => {
    if (get().edges.size || get().brought.size || get().shown) set({ edges: NONE, brought: NO_PAGES, shown: 0 });
  },
}));

/** A click on an edge: Cmd-, Ctrl- or Shift-click adds or removes it, a plain click keeps it alone (as pages are picked). */
export function clickEdge(l: Pick<SimLink, "source" | "target" | "kind">, ev: Pick<MouseEvent, "shiftKey" | "metaKey" | "ctrlKey">): void {
  const es = useEdgeSelect.getState();
  if (ev.shiftKey || ev.metaKey || ev.ctrlKey) es.toggle(l);
  else es.keep(l);
}

/**
 * The page selection leads: an edge stays kept only while both its pages are selected, so clearing the selection
 * (the background, Esc) or picking one page drops the edges as well.
 */
const unsubscribe = useKb.subscribe((s, prev) => {
  if (s.selection === prev.selection) return;
  const { edges, brought } = useEdgeSelect.getState();
  if (!edges.size && !brought.size) return;
  const kept = new Map([...edges].filter(([, [a, b]]) => s.selection.has(a) && s.selection.has(b)));
  const pages = new Set([...brought].filter((id) => s.selection.has(id)));
  if (kept.size !== edges.size || pages.size !== brought.size) useEdgeSelect.setState({ edges: kept.size ? kept : NONE, brought: pages.size ? pages : NO_PAGES });
});
// a reloaded module (dev) leaves no old subscriber writing to its old store
import.meta.hot?.dispose(unsubscribe);
