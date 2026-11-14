import { useLayoutEffect, useState, type RefObject } from "react";
import { useFlag } from "@/flags/useFlag";

/** Top of the search line inside the graph area. */
export const SHELL_TOP = 13;
/** With the app bar folding (flag `header-fold`) the line sits a little lower, under the chevron's 14px row. */
export const SHELL_TOP_FOLDED = 14;
/** Height of the search line (SearchBar's h-11). */
export const SEARCH_LINE_H = 44;

/** Where the search line sits now: lower while the app bar can fold, so the chevron above it has its own row. */
export function useShellTop(): number {
  return useFlag("header-fold") ? SHELL_TOP_FOLDED : SHELL_TOP;
}

/** Width of the left chat panel (flag `spark-chat`); the shell frame starts to its right so nothing overlaps. */
export const SPARK_PANEL_W = 400;

/** Chat sizes (flag `chat-full`): the folded right pane is a rail of this width. */
export const FULL_RAIL_W = 44;
/** Chat list column in the full chat. */
export const FULL_LIST_W = 232;
/** The right pane of the full chat (graph on top, page viewer below): half the width until its edge is dragged. */
export const FULL_PANE_W = "50%";

/** Width of the chat panel's box: the panel size, or the full chat up to the right pane (a rail when folded). */
export function chatPanelWidth(full: boolean, folded: boolean, panelW: number = SPARK_PANEL_W, paneW: number | null = null): string {
  if (!full) return `${panelW}px`;
  return `calc(100% - ${folded ? `${FULL_RAIL_W}px` : paneWidth(paneW)})`;
}

/** The right pane's width in the full chat: dragged by the edge between chat and graph, else the default share. */
export function paneWidth(paneW: number | null): string {
  // clamped where it is read too: a width saved on a wider window still leaves the chat its 480px
  return paneW ? `min(${paneW}px, calc(100% - 480px))` : FULL_PANE_W;
}

/**
 * Where the Concepts / Sources switch sits (variant `view-switch`): beside the search line, never inside it, so the
 * line stays the one place to search, ask, run a command or switch views by typing.
 * - quiet: a small flat segmented control left of the line, a 12px gap, shorter than the line (the default);
 * - words: two plain words left of the line, the chosen one underlined; icons: the quiet control, icons only;
 * - dock: joined to the line's left edge with one seam; tab: a small tab hanging under the line's centre.
 */
export const VIEW_SWITCH_IDS = ["quiet", "words", "icons", "dock", "tab"] as const;
export type ViewSwitchPlace = (typeof VIEW_SWITCH_IDS)[number];

/** The room the search line and its switch share: the line's own width, centred in the graph area. */
const ROW = "min(640px, calc(100% - 9rem))";
type Beside = Exclude<ViewSwitchPlace, "tab">;
const SWITCH_W: Record<Beside, number> = { quiet: 168, words: 132, icons: 68, dock: 172 };
const SWITCH_GAP: Record<Beside, number> = { quiet: 12, words: 16, icons: 12, dock: 0 };
/** Height of a switch that stands beside the line (the dock takes the line's own height). */
export const SWITCH_H = 32;
/** Below this graph-area width a switch beside the line would squeeze it, so every place falls back to the tab. */
export const VIEW_SWITCH_MIN_FRAME = 760;

/** The place actually used: the chosen one, or the tab while the graph area is too narrow for the line to share. */
export function placeFor(place: ViewSwitchPlace, frameWidth: number): ViewSwitchPlace {
  return frameWidth > 0 && frameWidth < VIEW_SWITCH_MIN_FRAME ? "tab" : place;
}

/**
 * The width of the graph area holding `ref` (its parent), kept current as panels open and close. Measured before the
 * first paint, so a narrow area never flashes the side-by-side place before falling back to the tab.
 */
export function useFrameWidth(ref: RefObject<HTMLElement | null>): number {
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    const frame = ref.current?.parentElement;
    if (!frame) return;
    setW(frame.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setW(frame.clientWidth));
    ro.observe(frame);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

export interface ViewSwitchBox {
  /** The search line's left edge and width (CSS lengths in the graph area). */
  barLeft: string;
  barWidth: string;
  /** The switch's left edge, width and offset from the line's top; a tab is centred and sized by its words. */
  left: string;
  width: number | null;
  dy: number;
  /** Which corners of the search line meet the switch and lose their rounding (the dock only). */
  square: "left" | null;
}

/** One geometry for both the line (GraphShell) and the switch (Corners), so the two always line up exactly. */
export function viewSwitchBox(place: ViewSwitchPlace | null): ViewSwitchBox {
  const start = `calc(50% - ${ROW} / 2)`;
  if (!place || place === "tab") return { barLeft: start, barWidth: ROW, left: "50%", width: null, dy: SEARCH_LINE_H - 1, square: null };
  const w = SWITCH_W[place];
  const g = SWITCH_GAP[place];
  const dock = place === "dock";
  return {
    barLeft: `calc(${start} + ${w + g}px)`,
    barWidth: `calc(${ROW} - ${w + g}px)`,
    left: start,
    width: w,
    dy: dock ? 0 : (SEARCH_LINE_H - SWITCH_H) / 2,
    square: dock ? "left" : null,
  };
}
