import { create } from "zustand";

/** Everything the corner controls can have open. `menu` and `edit` belong to a list or a fan. */
export type Layer = "pins" | "think" | "agent" | "legend" | "types" | "menu" | "edit";

export type MenuOwner = "pins" | "think" | "agent";
export type Edit = { kind: "pin" } | { kind: "rename"; id: string };

interface CornersState {
  /** open layers, oldest first: Esc closes the last one */
  order: Layer[];
  menu: { owner: MenuOwner; id?: string } | null;
  edit: Edit | null;
  /** the pinned view applied last (shown with a ring; what the "..." menu acts on) */
  activeView: string | null;

  has: (l: Layer) => boolean;
  /** Pins close both fans; a fan closes the pins; the two fans may be open together. */
  toggle: (l: "pins" | "think" | "agent" | "legend" | "types") => void;
  openMenu: (owner: MenuOwner, id?: string) => void;
  closeMenu: () => void;
  startEdit: (e: Edit) => void;
  endEdit: () => void;
  setActive: (id: string | null) => void;
  /** Close the topmost layer (Esc). Returns what it closed, or null when nothing was open. */
  closeTop: () => Layer | null;
  closeAll: () => void;
}

const without = (order: Layer[], ...drop: Layer[]) => order.filter((l) => !drop.includes(l));

type Snap = Pick<CornersState, "order" | "menu" | "edit">;

/** A menu or an inline edit only lives while the list or fan that owns it is open. */
function settle(order: Layer[], menu: Snap["menu"], edit: Snap["edit"]): Snap {
  const m = menu && order.includes(menu.owner) ? menu : null;
  const e = edit && order.includes("pins") ? edit : null;
  let o = order;
  if (!m) o = without(o, "menu");
  if (!e) o = without(o, "edit");
  return { order: o, menu: m, edit: e };
}

/** The two legends start open; one the user folds with its minus stays folded until they open it again. */
const LEGENDS: Layer[] = ["legend", "types"];
const FOLDED_KEY = "kb-graph-legends-folded";
function foldedLegends(): Set<Layer> {
  try {
    return new Set(JSON.parse(localStorage.getItem(FOLDED_KEY) ?? "[]") as Layer[]);
  } catch {
    return new Set();
  }
}
function rememberFolded(l: Layer, folded: boolean) {
  try {
    const s = foldedLegends();
    if (folded) s.add(l);
    else s.delete(l);
    localStorage.setItem(FOLDED_KEY, JSON.stringify([...s]));
  } catch {
    /* no storage: the legends simply start open */
  }
}
const openLegends = (): Layer[] => LEGENDS.filter((l) => !foldedLegends().has(l));
const keepLegends = (order: Layer[]) => order.filter((l) => LEGENDS.includes(l));

export const useCorners = create<CornersState>((set, get) => ({
  order: openLegends(),
  menu: null,
  edit: null,
  activeView: null,

  has: (l) => get().order.includes(l),
  toggle: (l) =>
    set((s) => {
      let base = s.order;
      if (LEGENDS.includes(l)) rememberFolded(l, base.includes(l));
      if (base.includes(l)) base = without(base, l);
      else {
        // pins close both fans, a fan closes the pins, the two fans may be open together
        if (l === "pins") base = without(base, "think", "agent");
        else if (l === "think" || l === "agent") base = without(base, "pins");
        // Think takes the right edge: the spread colour legend folds back so it never sits under the fan
        if (l === "think") base = without(base, "legend");
        base = [...base, l];
      }
      return settle(base, s.menu, s.edit);
    }),
  openMenu: (owner, id) => set((s) => settle([...without(s.order, "menu"), "menu"], { owner, id }, s.edit)),
  closeMenu: () => set((s) => settle(without(s.order, "menu"), null, s.edit)),
  startEdit: (edit) => set((s) => settle([...without(s.order, "menu", "edit"), "edit"], null, edit)),
  endEdit: () => set((s) => settle(without(s.order, "edit"), s.menu, null)),
  setActive: (activeView) => set({ activeView }),
  closeTop: () => {
    const { order, menu, edit } = get();
    // Esc closes fans, lists and menus; the legends close only with their own minus
    const top = [...order].reverse().find((l) => !LEGENDS.includes(l));
    if (!top) return null;
    set(settle(without(order, top), top === "menu" ? null : menu, top === "edit" ? null : edit));
    return top;
  },
  closeAll: () => set((s) => ({ order: keepLegends(s.order), menu: null, edit: null })),
}));

export const resetCorners = () => useCorners.setState({ order: [], menu: null, edit: null, activeView: null });
