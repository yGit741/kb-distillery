import { useMemo } from "react";
import { useTheme } from "@/theme/theme";
import { colorChannel } from "./encoding/channels";
import { RAMP_BY, effectiveColorBy, type ColorBy } from "./style";
import type { GNode } from "./types";

/** At most this many dots stand for the whole group: a schematic, not one dot per page. */
const DOTS = 18;

/**
 * The pages a view leaves out because none of its links reach them (Citations: papers with no `cites` link),
 * drawn as one small group at the side: a few dots in the view's colours, split like the counts, and a line per
 * colour. A click shows them on the canvas (the Connected filter off), like the legend's own filter chip.
 */
export function OutsideGroup({ nodes, colorBy, noun, empty = false, onShow }: { nodes: readonly GNode[]; colorBy: ColorBy; noun: string; empty?: boolean; onShow: () => void }) {
  const theme = useTheme((s) => s.theme);
  const by = effectiveColorBy(colorBy);
  const rows = useMemo(() => colorChannel(by, { ramp: RAMP_BY.has(by) ? theme : null }).rows(nodes), [nodes, by, theme]);
  const dots = useMemo(() => {
    const total = rows.reduce((s, r) => s + r.count, 0) || 1;
    // each colour keeps its share of the dots (at least one), so the group reads like the counts
    return rows.flatMap((r) => Array.from({ length: Math.max(1, Math.round((r.count / total) * DOTS)) }, () => r.color));
  }, [rows]);
  if (!nodes.length) return null;
  return (
    <button
      type="button"
      onClick={onShow}
      className="pointer-events-auto absolute bottom-24 left-4 z-[5] flex max-w-[15rem] flex-col gap-2 rounded-xl border bg-card/90 px-3 py-2.5 text-left text-xs shadow-[var(--shadow)] backdrop-blur-sm hover:bg-card"
      title={`Show the ${nodes.length} ${noun} on the graph`}
      data-testid="outside-group"
    >
      <span className="flex flex-wrap gap-1" aria-hidden>
        {dots.map((c, i) => (
          <i key={i} className="size-2 rounded-full" style={{ background: c }} />
        ))}
      </span>
      <span className="text-muted-foreground">
        <b className="font-medium text-foreground">{nodes.length}</b> {noun} not linked
      </span>
      {empty && <span className="text-muted-foreground">No citation links yet: fetch them with the citations command.</span>}
      <span className="flex flex-col gap-0.5">
        {rows.map((r) => (
          <span key={r.label} className="flex items-center gap-1.5">
            <i className="size-2 shrink-0 rounded-full" style={{ background: r.color }} aria-hidden />
            <span className="flex-1">{r.label}</span>
            <span className="tabular-nums text-muted-foreground">{r.count}</span>
          </span>
        ))}
      </span>
    </button>
  );
}
