import { ChevronDown } from "lucide-react";
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
  /** Inside the label rail: no floating card of its own. */
  embedded?: boolean;
}

const wide = () => typeof window === "undefined" || window.innerWidth >= 640;

/** Layer -> type -> depth legend. A row hides or shows its type; "Aa" labels every page of that type. */
export function Legend({ nodes, visible, schema, shownTypes, stats, embedded = false }: Props) {
  const ui = useGraphUi();
  const [open, setOpen] = useState(wide);
  const groups = useMemo(() => layerGroups(nodes, visible, schema, shownTypes), [nodes, visible, schema, shownTypes]);
  const depths = useMemo(() => depthRows(nodes, ui.shownDepths), [nodes, ui.shownDepths]);
  const key = useMemo(() => (ui.colorBy === "type" ? [] : colorKeyRows(nodes, visible, ui.colorBy)), [nodes, visible, ui.colorBy]);
  const allTypes = useMemo(() => groups.flatMap((g) => g.rows.map((r) => r.id)), [groups]);
  const defaults = schema.defaultVisible;
  const hasSources = groups.some((g) => g.layer === "source");

  return (
    <section
      aria-label="Legend"
      data-tour="graph-legend"
      className={cn(
        "pointer-events-auto flex flex-col text-sm",
        embedded
          ? "-mx-1"
          : "absolute bottom-3 left-3 z-10 max-h-[55%] w-[min(17rem,calc(100%-1.5rem))] rounded-lg border bg-card/95 shadow-[var(--shadow)]",
      )}
    >
      <header className="flex items-center gap-1 px-2.5 py-1.5">
        <button
          type="button"
          className="flex flex-1 items-center gap-1 text-left font-medium"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <ChevronDown aria-hidden className={cn("size-4 transition-transform", !open && "-rotate-90")} /> Legend
        </button>
        <button
          type="button"
          className="rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent"
          title="The concept layer: topics, ideas and questions (people are one chip away)"
          onClick={() => useGraphUi.setState({ shownTypes: undefined })}
        >
          Concepts only
        </button>
        <button
          type="button"
          className="rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent"
          onClick={() => useGraphUi.setState({ shownTypes: null })}
        >
          Show all
        </button>
      </header>
      {open && (
        <div className="overflow-y-auto px-2.5 pb-2">
          {groups.map((g) => (
            <div key={g.layer} className="mb-1.5">
              <button
                type="button"
                className="flex w-full items-center justify-between py-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground"
                aria-pressed={g.state === "all"}
                title={g.state === "none" ? `Show every ${g.layer}` : `Hide every ${g.layer}`}
                onClick={() =>
                  ui.setLayerTypes(
                    g.rows.map((r) => r.id),
                    g.state === "none",
                    allTypes,
                    defaults,
                  )
                }
              >
                <span>{LAYER_LABEL[g.layer]}</span>
                <span>{g.state === "some" ? "partly" : g.state === "none" ? "hidden" : g.total}</span>
              </button>
              <ul>
                {g.rows.map((r) => (
                  <li key={r.id} className={cn("flex items-center", !r.shown && "opacity-50")}>
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-accent"
                      aria-pressed={r.shown}
                      title={`${r.shown ? "Hide" : "Show"} every ${r.label.toLowerCase()}`}
                      onClick={() => ui.toggleType(r.id, allTypes, defaults)}
                    >
                      <Swatch color={typeColor(r.id)} />
                      <span className="truncate">{r.label}</span>
                      <small className="ml-auto text-muted-foreground">{r.total}</small>
                    </button>
                    <button
                      type="button"
                      className={cn(
                        "rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent disabled:opacity-30",
                        ui.typeLabels.has(r.id) && "bg-accent-soft text-primary",
                      )}
                      aria-pressed={ui.typeLabels.has(r.id)}
                      disabled={!r.shown}
                      title={`Labels for every ${r.label.toLowerCase()}`}
                      aria-label={`Labels for every ${r.label.toLowerCase()}`}
                      onClick={() => ui.toggleTypeLabels(r.id)}
                    >
                      Aa
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {hasSources && (
            <div className="mb-1.5">
              <div className="py-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">Depth of sources</div>
              <ul className="flex flex-wrap gap-1">
                {depths.map((d) => (
                  <li key={d.depth}>
                    <button
                      type="button"
                      className={cn(
                        "flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs hover:bg-accent",
                        !d.shown && "opacity-50",
                      )}
                      aria-pressed={d.shown}
                      title={`${d.shown ? "Hide" : "Show"} ${d.depth} sources`}
                      onClick={() => ui.toggleDepth(d.depth, DEPTHS)}
                    >
                      <Swatch color={depthColor(d.depth)} className="size-2" /> {d.depth} <small className="text-muted-foreground">{d.total}</small>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {key.length > 0 && (
            <div className="mb-1.5">
              <div className="py-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">Colour</div>
              <ul>
                {key.map((r) => (
                  <li key={r.label} className="flex items-center gap-2 px-1 py-0.5">
                    <Swatch color={r.color} />
                    <span className="truncate">{r.label}</span>
                    <small className="ml-auto text-muted-foreground">{r.count}</small>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="pt-1 text-xs text-muted-foreground" data-testid="graph-stats">
            {stats}
          </p>
        </div>
      )}
    </section>
  );
}
