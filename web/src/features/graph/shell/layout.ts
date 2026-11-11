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
/** The right pane of the full chat (graph on top, mini explorer below): up to this wide, at most this share of the width. */
export const FULL_PANE_W = "min(48%, 720px)";

/** Width of the chat panel's box: the panel size, or the full chat up to the right pane (a rail when folded). */
export function chatPanelWidth(full: boolean, folded: boolean, panelW: number = SPARK_PANEL_W, paneW: number | null = null): string {
  if (!full) return `${panelW}px`;
  return `calc(100% - ${folded ? `${FULL_RAIL_W}px` : paneWidth(paneW)})`;
}

/** The right pane's width in the full chat: dragged by the edge between chat and graph, else the default share. */
export function paneWidth(paneW: number | null): string {
  return paneW ? `${paneW}px` : FULL_PANE_W;
}
