import { IS_SHARE } from "@/share/env";
import { LINE_COPY } from "./shell/copy";
import type { GNode } from "./types";

/** What a node-menu action may do. */
export interface MenuContext {
  openReader: (id: string) => void;
  openDetails: (id: string) => void;
  openPage: (id: string) => void;
  /** Result and set actions (flag graph-intent); the plain node menu leaves them out. */
  focus?: (id: string) => void;
  showOnly?: (ids: string[], label: string) => void;
  addToView?: (ids: string[], label: string) => void;
  expand?: (id: string) => void;
  colorSet?: (ids: string[], label: string) => void;
  chat?: (ids: string[]) => void;
  think?: (id: string) => void;
  highlight?: (ids: string[]) => void;
}

/**
 * The right-click menu on a node. `when` offers an entry at all, `enabled` greys it out with `why`.
 * A new action is one more entry here (or `registerMenuItem` from a tool); the 2-hop citation
 * genealogy lands with the data layer.
 */
export interface MenuItem {
  id: string;
  label: string;
  hint?: string;
  when?: (n: GNode) => boolean;
  enabled?: (n: GNode) => boolean;
  why?: string;
  run: (n: GNode, ctx: MenuContext) => void;
}

export const MENU_ITEMS: MenuItem[] = [
  { id: "reader", label: "Open in side reader", hint: "double-click", run: (n, c) => c.openReader(n.id) },
  { id: "details", label: "Show details", hint: "links · sources", run: (n, c) => c.openDetails(n.id) },
  { id: "page", label: "Open in Pages", hint: "E", run: (n, c) => c.openPage(n.id) },
];

export function registerMenuItem(item: MenuItem, before?: string): void {
  const without = MENU_ITEMS.filter((i) => i.id !== item.id);
  const at = before ? without.findIndex((i) => i.id === before) : -1;
  MENU_ITEMS.length = 0;
  MENU_ITEMS.push(...(at >= 0 ? [...without.slice(0, at), item, ...without.slice(at)] : [...without, item]));
}

export const visibleItems = (n: GNode, items: readonly MenuItem[] = MENU_ITEMS): MenuItem[] =>
  items.filter((i) => !i.when || i.when(n));

const A = LINE_COPY.actions;

/**
 * The action menu: the same one for a search result, a set, the focus and the view (flag graph-intent). The plain
 * node menu above keeps MENU_ITEMS. Favorite and export are slots, greyed out until their features land.
 */
export const ACTION_ITEMS: MenuItem[] = [
  { id: "focus", label: A.focus.label, hint: A.focus.hint, run: (n, c) => c.focus?.(n.id) },
  { id: "show", label: A.show.label, hint: A.show.hint, run: (n, c) => c.showOnly?.([n.id], n.title || n.id) },
  { id: "read", label: A.read.label, hint: A.read.hint, run: (n, c) => c.openReader(n.id) },
  { id: "expand", label: A.expand.label, hint: A.expand.hint, run: (n, c) => c.expand?.(n.id) },
  { id: "favorite", label: A.favorite.label, enabled: () => false, why: A.favorite.why, run: () => {} },
  { id: "chat", label: A.chat.label, hint: A.chat.hint, when: () => !IS_SHARE, run: (n, c) => c.chat?.([n.id]) },
  { id: "think", label: A.think.label, hint: A.think.hint, when: () => !IS_SHARE, run: (n, c) => c.think?.(n.id) },
  { id: "export", label: A.export.label, enabled: () => false, why: A.export.why, run: () => {} },
];

/** The same menu for a set of pages: the actions act on all of them. */
export const setActionItems = (ids: string[], label: string): MenuItem[] => [
  { id: "highlight", label: A.highlight.label, hint: A.highlight.hint, run: (_n, c) => c.highlight?.(ids) },
  { id: "show", label: A.showSet.label, hint: A.showSet.hint, run: (_n, c) => c.showOnly?.(ids, label) },
  { id: "add", label: A.addToView.label, hint: A.addToView.hint, run: (_n, c) => c.addToView?.(ids, label) },
  { id: "color", label: A.color.label, hint: A.color.hint, run: (_n, c) => c.colorSet?.(ids, label) },
  { id: "chat", label: A.chatSet.label, hint: A.chatSet.hint, run: (_n, c) => c.chat?.(ids) },
];
