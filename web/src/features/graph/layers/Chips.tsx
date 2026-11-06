import { Undo2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useKb } from "@/lib/store";
import { cn } from "@/lib/utils";
import { useGraphUi } from "../store";
import type { ColorBy } from "../style";
import type { GNode } from "../types";
import { marker } from "../shell/shape";
import { describe, mainParam, withParam, type Layer, type MainParam } from "./model";
import { stackCurrent, useLayers } from "./store";

const CHIP = "inline-flex min-h-6 max-w-[16rem] items-center gap-1 rounded-full px-2 py-0.5 text-xs";
const REMOVE = "grid size-4 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring";
const COLOURS: readonly ColorBy[] = ["type", "layer", "area", "depth", "status", "degree"];

/** The small inline editor of a chip's main parameter: hops, the node, the link type or the colour. */
function Editor({ layer, param, onDone }: { layer: Layer; param: MainParam; onDone: () => void }) {
  const [value, setValue] = useState(param.kind === "hops" ? String(param.n) : param.value);
  const ref = useRef<HTMLInputElement | HTMLSelectElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const save = (v: string) => {
    const next: MainParam = param.kind === "hops" ? { kind: "hops", n: Number(v) || param.n } : { ...param, value: v };
    useLayers.getState().edit(layer.id, withParam(layer, next));
    onDone();
  };
  const label = { hops: "Hops", node: "Page", edgeType: "Link type", color: "Colour by" }[param.kind];
  return (
    <div role="group" aria-label={`Edit ${describe(layer)}`} className="absolute left-0 top-full z-20 mt-1 flex items-center gap-1.5 rounded-lg border bg-popover p-1.5 text-xs shadow-[var(--shadow)]">
      <label className="flex items-center gap-1.5 text-muted-foreground">
        {label}
        {param.kind === "color" ? (
          <select
            ref={ref as React.RefObject<HTMLSelectElement>}
            className="rounded border bg-transparent px-1 py-0.5 text-foreground"
            value={value}
            onChange={(e) => save(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && onDone()}
          >
            {COLOURS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : (
          <input
            ref={ref as React.RefObject<HTMLInputElement>}
            className="w-28 rounded border bg-transparent px-1 py-0.5 text-foreground"
            type={param.kind === "hops" ? "number" : "text"}
            min={1}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save(value);
              else if (e.key === "Escape") onDone();
              e.stopPropagation();
            }}
          />
        )}
      </label>
      {param.kind !== "color" && (
        <button type="button" className="rounded px-1.5 py-0.5 text-primary hover:bg-accent" onClick={() => save(value)}>
          Apply
        </button>
      )}
    </div>
  );
}

/**
 * The two chip rows under the search line (flag graph-intent). Focus: one light chip per focused page, remove =
 * deselect. View: one solid chip per layer in plain words, remove = drop the layer, click = edit its main parameter.
 * An empty row renders nothing.
 */
export function Chips({ byId }: { byId: ReadonlyMap<string, GNode> }) {
  const selection = useKb((s) => s.selection);
  const layers = useLayers((s) => s.stack.layers);
  const canUndo = useLayers((s) => s.history.length > 0);
  const applied = useLayers((s) => s.applied);
  const live = useGraphUi((s) => stackCurrent(applied, marker(s)));
  const [editing, setEditing] = useState<string | null>(null);
  const focus = [...selection];
  if (!focus.length && !layers.length && !canUndo) return null;
  return (
    <div className="pointer-events-auto mt-1.5 flex flex-col gap-1" data-testid="chip-rows">
      {focus.length > 0 && (
        <div role="group" aria-label="Focus" className="flex flex-wrap items-center gap-1">
          {focus.map((id) => {
            const name = byId.get(id)?.title || id;
            return (
              <span key={id} className={cn(CHIP, "border bg-card text-foreground")}>
                <span className="truncate">{name}</span>
                <button type="button" className={REMOVE} aria-label={`Remove ${name} from the focus`} onClick={() => useKb.getState().deselect(id)}>
                  <X aria-hidden className="size-3" strokeWidth={1.6} />
                </button>
              </span>
            );
          })}
        </div>
      )}
      {(layers.length > 0 || canUndo) && (
        <div role="group" aria-label="View" className="flex flex-wrap items-center gap-1">
          {layers.map((l) => {
            const text = describe(l);
            const param = mainParam(l);
            return (
              <span key={l.id} className={cn("relative", !live && "opacity-60")} title={live ? undefined : "Changed by hand since this was applied"}>
                <span className={cn(CHIP, "bg-accent-soft text-primary")}>
                  {param ? (
                    <button type="button" className="truncate rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-ring" aria-expanded={editing === l.id} onClick={() => setEditing(editing === l.id ? null : l.id)}>
                      {text}
                    </button>
                  ) : (
                    <span className="truncate">{text}</span>
                  )}
                  <button type="button" className={REMOVE} aria-label={`Remove ${text}`} onClick={() => useLayers.getState().apply("remove", l.id)}>
                    <X aria-hidden className="size-3" strokeWidth={1.6} />
                  </button>
                </span>
                {editing === l.id && param && <Editor layer={l} param={param} onDone={() => setEditing(null)} />}
              </span>
            );
          })}
          {canUndo && (
            <button type="button" className={cn(CHIP, "text-muted-foreground hover:bg-accent hover:text-foreground")} title="Undo the last change (Cmd-Z)" onClick={() => useLayers.getState().undo()}>
              <Undo2 aria-hidden className="size-3" strokeWidth={1.6} />
              Undo
            </button>
          )}
        </div>
      )}
    </div>
  );
}
