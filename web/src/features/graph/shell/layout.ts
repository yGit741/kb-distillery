import { useFlag } from "@/flags/useFlag";

/** Top of the search line inside the graph area. */
export const SHELL_TOP = 13;
/** With the app bar folding (flag `header-fold`) the line sits lower, under the chevron's 24px row. */
export const SHELL_TOP_FOLDED = 28;
/** Height of the search line (SearchBar's h-11). */
export const SEARCH_LINE_H = 44;

/** Where the search line sits now: lower while the app bar can fold, so the chevron above it has its own row. */
export function useShellTop(): number {
  return useFlag("header-fold") ? SHELL_TOP_FOLDED : SHELL_TOP;
}

/** Width of the left chat panel (flag `spark-chat`); the shell frame starts to its right so nothing overlaps. */
export const SPARK_PANEL_W = 400;
