import { create } from "zustand";
import { flag } from "@/flags";

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
  /** flag graph.artifacts: the card of the pin's loop whose pile of views is unfolded into a row (one at a time) */
  pile: string | null;
  /** flag graph.artifacts: the unfolded card whose "?" explanation is open */
  about: string | null;
  /** how far down from the graph area's top the unfolded cards reach, px (the loop reports it; the graph frames below it) */
  pileReach: number;

  has: (l: Layer) => boolean;
  /** Pins close both fans; a fan closes the pins; the two fans may be open together. */
  /** `remember: false` for a toggle the app makes itself (a view opening or folding the legend): only the user's own
   *  minus or opener is saved */
  toggle: (l: "pins" | "think" | "agent" | "legend" | "types", opts?: { remember?: boolean }) => void;
  openMenu: (owner: MenuOwner, id?: string) => void;
  closeMenu: () => void;
  startEdit: (e: Edit) => void;
  endEdit: () => void;
  setActive: (id: string | null) => void;
  setPile: (key: string | null) => void;
  setPileReach: (px: number) => void;
  setAbout: (key: string | null) => void;
  /** flag graph-corners: open both legends, once per page load */
  openLegendsOnce: () => void;
  /** Close the topmost layer (Esc). Returns what it closed, or null when nothing was open. An unfolded pile folds first. */
  closeTop: () => Layer | "pile" | null;
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

/**
 * The two legends start open; one the user folds with its minus stays folded until they open it again. Under flag
 * graph-corners a fold lasts until the page reloads: every visit opens on the legend.
 */
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
/** once per page load (flag graph-corners): the legends open whatever an earlier visit folded */
let legendsReopened = false;
const keepLegends = (order: Layer[]) => order.filter((l) => LEGENDS.includes(l));

export const useCorners = create<CornersState>((set, get) => ({
  order: openLegends(),
  menu: null,
  edit: null,
  activeView: null,
  pile: null,
  pileReach: 0,
  about: null,

  has: (l) => get().order.includes(l),
  toggle: (l, opts) =>
    set((s) => {
      let base = s.order;
      if (LEGENDS.includes(l) && opts?.remember !== false && !flag("graph-corners")) rememberFolded(l, base.includes(l));
      if (base.includes(l)) base = without(base, l);
      else {
        // pins close both fans, a fan closes the pins, the two fans may be open together
        if (l === "pins") base = without(base, "think", "agent");
        else if (l === "think" || l === "agent") base = without(base, "pins");
        // Think takes the right edge: the spread colour legend folds back so it never sits under the fan
        if (l === "think") base = without(base, "legend");
        base = [...base, l];
      }
      // a pile only stays unfolded while the loop it belongs to is open
      const open = base.includes("pins");
      return { ...settle(base, s.menu, s.edit), pile: open ? s.pile : null, about: open ? s.about : null };
    }),
  openMenu: (owner, id) => set((s) => settle([...without(s.order, "menu"), "menu"], { owner, id }, s.edit)),
  closeMenu: () => set((s) => settle(without(s.order, "menu"), null, s.edit)),
  startEdit: (edit) => set((s) => settle([...without(s.order, "menu", "edit"), "edit"], null, edit)),
  endEdit: () => set((s) => settle(without(s.order, "edit"), s.menu, null)),
  setActive: (activeView) => set({ activeView }),
  // an explanation belongs to a card of the row: it closes when the row folds or another one unfolds
  setPile: (pile) => set({ pile, about: null }),
  setAbout: (about) => set({ about }),
  setPileReach: (pileReach) => set({ pileReach }),
  openLegendsOnce: () => {
    if (legendsReopened) return;
    legendsReopened = true;
    // a fold remembered before graph-corners (or by another tab) does not carry into this page load
    set((s) => settle([...LEGENDS.filter((l) => !(l === "legend" && s.order.includes("think"))), ...without(s.order, ...LEGENDS)], s.menu, s.edit));
  },
  closeTop: () => {
    const { order, menu, edit } = get();
    // Esc closes fans, lists and menus; the legends close only with their own minus
    const top = [...order].reverse().find((l) => !LEGENDS.includes(l));
    if (!top) return null;
    // an open explanation closes first, then the row folds, then the loop closes
    if (top === "pins" && get().about) {
      set({ about: null });
      return "pile";
    }
    if (top === "pins" && get().pile) {
      set({ pile: null });
      return "pile";
    }
    set(settle(without(order, top), top === "menu" ? null : menu, top === "edit" ? null : edit));
    return top;
  },
  closeAll: () => set((s) => ({ order: keepLegends(s.order), menu: null, edit: null, pile: null, about: null })),
}));

export const resetCorners = () => useCorners.setState({ order: [], menu: null, edit: null, activeView: null, pile: null, pileReach: 0, about: null });
