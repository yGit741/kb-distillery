import { useTheme } from "@/theme/theme";
import { colorOf, effectiveColorBy, RAMP_BY, type ColorBy } from "./style";
import type { GNode } from "./types";

/**
 * A page's colour for the swatch next to its name (inspector, menu, search results, hover card): the same as its
 * node on the canvas. An ordered colouring (depth, link count, ...) uses the theme's one ramp there, so a chip
 * never shows a different colour than the page it names. Read when the swatch renders (these are short-lived
 * surfaces; the theme toggle re-renders them).
 */
export function swatchColor(n: GNode, colorBy: ColorBy): string {
  const by = effectiveColorBy(colorBy);
  return colorOf(n, by, undefined, RAMP_BY.has(by) ? useTheme.getState().theme : null);
}
