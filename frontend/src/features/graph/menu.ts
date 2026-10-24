import type { GNode } from "./types";

/** What a node-menu action may do. */
export interface MenuContext {
  openReader: (id: string) => void;
  openDetails: (id: string) => void;
  openPage: (id: string) => void;
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
