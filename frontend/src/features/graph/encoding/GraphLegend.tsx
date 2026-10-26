import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { NO_AREA, OTHER_AREAS } from "../style";
import type { GNode } from "../types";
import type { ColorChannel, KeyRow, SizeChannel } from "./channels";
import { ShapeIcon, SourceIcon } from "./NodeMarkSvg";
import { GLYPH_LABEL, glyphOf, markOf, type NodeMark, type SourceGlyph } from "./spec";

/** The Type row's order: concepts first (what I think with), then people, collections, sources (what I read). */
const TYPE_ORDER: readonly { mark: NodeMark; label: string }[] = [
  { mark: "topic", label: "Topic" },
  { mark: "idea", label: "Idea" },
  { mark: "question", label: "Question" },
  { mark: "person", label: "Person" },
  { mark: "collection", label: "Collection" },
  { mark: "source", label: "Source" },
];
const GLYPH_ORDER = Object.keys(GLYPH_LABEL) as SourceGlyph[];

/** A colour value's swatch: a dot, or a ring for "No area" (its faint grey must never read as "Other areas"). */
export function LegendSwatch({ row, className }: { row: Pick<KeyRow, "label" | "color">; className?: string }) {
  return row.label === NO_AREA ? (
    <i aria-hidden className={cn("inline-block size-2.5 shrink-0 rounded-full border-2", className)} style={{ borderColor: row.color }} />
  ) : (
    <i aria-hidden className={cn("inline-block size-2.5 shrink-0 rounded-full", className)} style={{ background: row.color }} />
  );
}

/** A row's title, the same everywhere: "Type", "Sources", "Colour = theme", "Size = links". */
export function LegendTitle({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("shrink-0 text-[10px] font-medium uppercase tracking-wide text-muted-foreground", className)}>{children}</span>;
}

/** Marks present in these pages, in the Type row's order, with counts. */
export function typeRows(nodes: readonly Pick<GNode, "type">[]): { mark: NodeMark; label: string; count: number }[] {
  const count = new Map<NodeMark, number>();
  for (const n of nodes) count.set(markOf(n.type), (count.get(markOf(n.type)) ?? 0) + 1);
  return TYPE_ORDER.filter((t) => count.get(t.mark)).map((t) => ({ ...t, count: count.get(t.mark)! }));
}

/** Source glyphs present in these pages, with counts (a sample type per glyph, for its icon). */
export function glyphRows(nodes: readonly Pick<GNode, "type">[]): { glyph: SourceGlyph; type: string; label: string; count: number }[] {
  const seen = new Map<SourceGlyph, { type: string; count: number }>();
  for (const n of nodes) {
    if (markOf(n.type) !== "source") continue;
    const g = glyphOf(n.type);
    const s = seen.get(g) ?? { type: n.type, count: 0 };
    s.count += 1;
    seen.set(g, s);
  }
  return GLYPH_ORDER.filter((g) => seen.has(g)).map((g) => ({ glyph: g, type: seen.get(g)!.type, label: GLYPH_LABEL[g], count: seen.get(g)!.count }));
}

interface Props {
  nodes: readonly GNode[];
  color: ColorChannel;
  size?: SizeChannel | null;
  /** full: one row per encoding; compact: one wrapping line, for a card */
  density?: "full" | "compact";
  /** compact: at most this many colour values, the rest folded into "+N" (its title lists them) */
  maxColors?: number;
  className?: string;
}

/**
 * The legend under every graph: a Type row (only the marks drawn), a Sources row (the glyphs drawn), a Colour row
 * titled by the surface's colour channel, and a Size row when size varies. One component, two densities.
 */
export function GraphLegend({ nodes, color, size, density = "full", maxColors = 8, className }: Props) {
  const types = typeRows(nodes);
  const glyphs = glyphRows(nodes);
  const all = color.rows(nodes);
  const compact = density === "compact";
  // an ordered ramp is never cut: its steps read only as a whole
  const shown = compact && !color.ramp ? all.slice(0, maxColors) : all;
  const rest = all.slice(shown.length);
  const item = "inline-flex shrink-0 items-center gap-1";
  // compact: each row is one unit (its title never wraps away from its values)
  const row = compact ? "inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-0.5" : "flex flex-wrap items-center gap-x-2.5 gap-y-0.5";
  // rows are set apart by space, not rules: a rule would dangle at a line end when the legend wraps
  return (
    <div
      role="group"
      aria-label="Legend"
      data-density={density}
      className={cn(compact ? "flex flex-wrap items-center gap-x-4 gap-y-0.5 text-[11px] leading-4" : "flex flex-col gap-1 text-xs", "text-foreground", className)}
    >
      <div className={row} data-row="type">
        <LegendTitle>Type</LegendTitle>
        {types.map((t) => (
          <span key={t.mark} className={item} title={`${t.count} ${t.label.toLowerCase()}${t.count === 1 ? "" : "s"}`}>
            <ShapeIcon shape={t.mark} className="size-3" />
            {t.label}
          </span>
        ))}
      </div>
      {glyphs.length > 0 && (
        <>
          <div className={row} data-row="sources">
            <LegendTitle>Sources</LegendTitle>
            {glyphs.map((g) => (
              <span key={g.glyph} className={item} title={`${g.count} ${g.label.toLowerCase()}`}>
                <SourceIcon type={g.type} className="size-3" />
                {g.label}
              </span>
            ))}
          </div>
        </>
      )}
      <div className={row} data-row="colour">
        <LegendTitle>Colour = {color.title}</LegendTitle>
        {color.ramp && <span className="text-muted-foreground">{color.ramp.low}</span>}
        {shown.map((r) => (
          <span key={r.label} className={item} title={`${r.label}: ${r.count}`}>
            <LegendSwatch row={r} />
            {!color.ramp && <span className={cn((r.label === NO_AREA || r.label === OTHER_AREAS) && "italic text-muted-foreground")}>{r.label}</span>}
          </span>
        ))}
        {color.ramp && <span className="text-muted-foreground">{color.ramp.high}</span>}
        {rest.length > 0 && (
          <span className="text-muted-foreground" title={rest.map((r) => r.label).join(", ")}>
            +{rest.length}
          </span>
        )}
      </div>
      {size && (
        <>
          <div className={row} data-row="size">
            <LegendTitle>Size = {size.title}</LegendTitle>
            <span className={item} aria-hidden>
              <i className="inline-block size-1.5 rounded-full bg-muted-foreground" />
              <i className="inline-block size-2.5 rounded-full bg-muted-foreground" />
            </span>
          </div>
        </>
      )}
    </div>
  );
}
