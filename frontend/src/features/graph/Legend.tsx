import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { depthColor, typeColor } from "@/theme/palette";
import { Swatch } from "./controls";
import { colorKeyRows, depthRows, LAYER_LABEL, layerGroups } from "./legendModel";
import type { GraphSchema } from "./schema";
import { useGraphUi } from "./store";
import type { GNode } from "./types";
import { DEPTHS } from "@/api/model";

interface Props {
  nodes: readonly GNode[];
  visible: ReadonlySet<string>;
  schema: GraphSchema;
  shownTypes: ReadonlySet<string> | null;
  stats: string;
}

const CHIP = "flex shrink-0 items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs hover:bg-accent";
const GROUP = "shrink-0 px-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground";

/**
 * The legend as one compact bar along the bottom: layer -> type chips (click hides or shows the type), source
 * depths, and the colour key when colour is not by type. "Aa" switches the chips to labelling every page of a type.
 */
export function Legend({ nodes, visible, schema, shownTypes, stats }: Props) {
  const ui = useGraphUi();
  const [labelMode, setLabelMode] = useState(false);
  const groups = useMemo(() => layerGroups(nodes, visible, schema, shownTypes), [nodes, visible, schema, shownTypes]);
  const depths = useMemo(() => depthRows(nodes, ui.shownDepths), [nodes, ui.shownDepths]);
  const key = useMemo(() => (ui.colorBy === "type" ? [] : colorKeyRows(nodes, visible, ui.colorBy)), [nodes, visible, ui.colorBy]);
  const allTypes = useMemo(() => groups.flatMap((g) => g.rows.map((r) => r.id)), [groups]);
  const defaults = schema.defaultVisible;
  const hasSources = groups.some((g) => g.layer === "source" && g.state !== "none");

  return (
    <section
      aria-label="Legend"
      data-tour="graph-legend"
      title={stats}
      className="pointer-events-auto absolute bottom-3 left-1/2 z-10 flex max-w-[calc(100%-1.5rem)] -translate-x-1/2 items-center gap-1 rounded-lg border bg-card/95 px-1.5 py-1 shadow-[var(--shadow)]"
    >
      {/* the chips scroll sideways on a narrow screen; the controls on the right stay put */}
      <div className="flex min-w-0 items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {groups.map((g) => (
        <div key={g.layer} className="flex shrink-0 items-center gap-0.5 border-r pr-1 last-of-type:border-r-0">
          <button
            type="button"
            className={GROUP}
            aria-pressed={g.state === "all"}
            title={g.state === "none" ? `Show every ${g.layer}` : `Hide every ${g.layer}`}
            onClick={() => ui.setLayerTypes(g.rows.map((r) => r.id), g.state === "none", allTypes, defaults)}
          >
            {LAYER_LABEL[g.layer]}
          </button>
          {g.rows.map((r) => {
            const labelled = ui.typeLabels.has(r.id);
            return (
              <button
                key={r.id}
                type="button"
                className={cn(CHIP, !r.shown && "opacity-40", labelMode && labelled && "bg-accent-soft text-primary")}
                aria-pressed={labelMode ? labelled : r.shown}
                disabled={labelMode && !r.shown}
                title={labelMode ? `Labels for every ${r.label.toLowerCase()}` : `${r.shown ? "Hide" : "Show"} every ${r.label.toLowerCase()}`}
                onClick={() => (labelMode ? ui.toggleTypeLabels(r.id) : ui.toggleType(r.id, allTypes, defaults))}
              >
                <Swatch color={typeColor(r.id)} className="size-2" />
                <span className={cn(labelled && "font-semibold")}>{r.label}</span>
                <small className="text-muted-foreground">{r.total}</small>
              </button>
            );
          })}
        </div>
      ))}
      {hasSources && (
        <div className="flex shrink-0 items-center gap-0.5 border-r pr-1">
          <span className={cn(GROUP, "hover:text-muted-foreground")}>Depth</span>
          {depths.map((d) => (
            <button
              key={d.depth}
              type="button"
              className={cn(CHIP, !d.shown && "opacity-40")}
              aria-pressed={d.shown}
              title={`${d.shown ? "Hide" : "Show"} ${d.depth} sources`}
              onClick={() => ui.toggleDepth(d.depth, DEPTHS)}
            >
              <Swatch color={depthColor(d.depth)} className="size-2" /> {d.depth} <small className="text-muted-foreground">{d.total}</small>
            </button>
          ))}
        </div>
      )}
      {key.length > 0 && (
        <div className="flex shrink-0 items-center gap-1.5 border-r px-1 text-xs">
          {key.map((r) => (
            <span key={r.label} className="flex items-center gap-1">
              <Swatch color={r.color} className="size-2" /> {r.label} <small className="text-muted-foreground">{r.count}</small>
            </span>
          ))}
        </div>
      )}
      </div>
      <button
        type="button"
        className={cn(CHIP, "border-l font-medium", labelMode && "bg-accent-soft text-primary")}
        aria-pressed={labelMode}
        title="Label mode: a chip click labels every page of its type"
        onClick={() => setLabelMode(!labelMode)}
      >
        Aa
      </button>
      <button type="button" className={cn(CHIP, "text-muted-foreground")} title="The concept layer: topics, ideas and questions" onClick={() => useGraphUi.setState({ shownTypes: undefined })}>
        Concepts only
      </button>
      <button type="button" className={cn(CHIP, "text-muted-foreground")} onClick={() => useGraphUi.setState({ shownTypes: null })}>
        Show all
      </button>
      <span className="sr-only" data-testid="graph-stats">
        {stats}
      </span>
    </section>
  );
}
