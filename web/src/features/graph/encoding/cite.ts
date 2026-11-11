import { withAlpha, type CanvasColors } from "./theme";
import { drawNode } from "./canvas";
import { SOURCE_GLYPH_PX } from "./spec";
import type { SimNode } from "../types";

/**
 * The one encoding of a paper in a citation drawing (the genealogy drawer and the corpus-wide citation map): a
 * source dot with the page glyph, size = citations (log), the label `title (year)` on the focus and on hover.
 */
export type CiteNode = SimNode & { citations: number };

/** A citation node as a graph node: every node is a paper (a source). */
export function citeNode<T extends object>(n: { id: string; title: string; year?: number | null; citationCount: number }, extra: T): CiteNode & T {
  return {
    id: n.id,
    label: n.title,
    title: n.title,
    type: "paper",
    layer: "source",
    maturity: "",
    depth: "",
    areas: [],
    year: n.year ?? null,
    inDegree: 0,
    outDegree: 0,
    path: "",
    added: "",
    changed: "",
    preview: "",
    properties: {},
    citations: n.citationCount,
    ...extra,
  } as CiteNode & T;
}

/** Size = citations, on a log scale, capped. */
export const citeRadius = (citations: number | undefined): number => 3 + Math.min(Math.log2(1 + (citations ?? 0)), 7);

export const citeLabel = (n: Pick<SimNode, "title" | "year">): string => `${n.title}${n.year ? ` (${n.year})` : ""}`;

export interface CiteDrawOpts {
  r: number;
  color: string;
  colors: CanvasColors;
  state: "focus" | "hover" | null;
  /** draw the `title (year)` label under the dot */
  label: boolean;
  faded?: boolean;
}

export function drawCite(n: SimNode, ctx: CanvasRenderingContext2D, scale: number, o: CiteDrawOpts): void {
  if (n.x == null || n.y == null) return;
  const c = o.colors;
  drawNode(ctx, n.type, {
    x: n.x,
    y: n.y,
    r: o.r,
    color: o.color,
    background: c.background,
    font: c.font,
    ring: c.ring,
    state: o.state,
    alpha: o.faded ? 0.35 : 1,
    glyph: o.r * scale >= SOURCE_GLYPH_PX || o.state === "hover",
    scale,
  });
  if (!o.label) return;
  const size = Math.max(11 / scale, 3);
  ctx.font = `${size}px ${c.font}`;
  const text = citeLabel(n);
  const w = ctx.measureText(text).width;
  ctx.fillStyle = withAlpha(c.background, 0.88);
  ctx.fillRect(n.x - w / 2 - 2 / scale, n.y + o.r + 3 / scale, w + 4 / scale, size + 3 / scale);
  ctx.fillStyle = c.text;
  ctx.fillText(text, n.x - w / 2, n.y + o.r + 3 / scale + size);
}
