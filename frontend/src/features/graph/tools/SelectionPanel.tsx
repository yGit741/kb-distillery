import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useDataSource } from "@/api";
import { Button } from "@/components/ui/button";
import { useKb } from "@/lib/store";
import { buildNeighborMap } from "../graphData";
import { useLayer } from "../layerStore";
import {
  citationNeighbours,
  memberSources,
  neighboursOf,
  onlyType,
  pageIds,
  routeOf,
  typesOf,
  visibleAdjacency,
} from "../selection";
import { useGraphUi } from "../store";
import type { GraphToolContext } from ".";

/** Draw pages the type filter hides: a selection must be visible. */
export function revealIds(ids: Iterable<string>): void {
  useGraphUi.setState((s) => ({ revealed: new Set([...s.revealed, ...ids]) }));
}

const STALE = 5 * 60_000;

/**
 * Select, expand, collapse, find a path: every way to grow or shrink the selection is a button here.
 * Box and lasso are the right mouse button on the canvas (help panel).
 */
export function SelectionPanel({ ctx }: { ctx: GraphToolContext }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const expansions = useLayer((s) => s.expansions);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const ids = useMemo(() => pageIds(ctx.selection, ctx.byId), [ctx.selection, ctx.byId]);
  const all = useMemo(() => buildNeighborMap(ctx.model.links), [ctx.model]);
  const types = useMemo(() => typesOf(ids, ctx.byId), [ids, ctx.byId]);

  const grow = (found: string[], what: string) => {
    if (!found.length) {
      setNote(`No new ${what} to add.`);
      return;
    }
    revealIds(found);
    useLayer.getState().pushExpansion(found);
    ctx.select(found, { additive: true });
    setNote(`Added ${found.length} ${what}.`);
  };

  const neighbours = () => grow(neighboursOf(ids, visibleAdjacency(ctx.model.links, ctx.visible)), "neighbouring pages");
  const sources = () => grow(memberSources(ids, all, ctx.byId), "source pages");
  const citations = async () => {
    setBusy(true);
    try {
      const c = await qc.fetchQuery({ queryKey: ["citations"], queryFn: () => ds.getCitations(), staleTime: STALE });
      if (c.missing || !c.links.length) setNote("No citation data yet: run python3 -m kb.search.citations fetch.");
      else grow(citationNeighbours(new Set(ids), c.links, new Set(ctx.byId.keys())), "citing or cited pages");
    } catch (e) {
      setNote(`Could not load citations: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };
  const collapse = () => {
    const last = useLayer.getState().popExpansion();
    for (const id of last) useKb.getState().deselect(id);
    setNote(last.length ? `Took back ${last.length} page${last.length === 1 ? "" : "s"}.` : "");
  };
  const path = async () => {
    const [a, b] = ids;
    if (!a || !b) return;
    setBusy(true);
    try {
      const res = await ds.findPath(a, b);
      const route = routeOf(res);
      if (!route.length) {
        setNote("These two pages are not connected.");
        return;
      }
      revealIds(route);
      useLayer.getState().pushExpansion(route.filter((id) => !ctx.selection.has(id)));
      ctx.select(route, { additive: true });
      setNote(`Path of ${route.length} pages (${res.distance ?? route.length - 1} link${(res.distance ?? route.length - 1) === 1 ? "" : "s"}) added.`);
    } catch (e) {
      setNote(`Path failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 text-sm">
      <p role="status" aria-live="polite">
        <b>{ids.length}</b> selected{types.length > 1 ? ` · ${types.length} types` : ""}
      </p>
      <div className="grid grid-cols-2 gap-1.5">
        <Button size="sm" variant="outline" disabled={!ids.length} onClick={neighbours} title="Add everything one link away over the drawn links (repeatable)">
          + Neighbours
        </Button>
        <Button size="sm" variant="outline" disabled={!ids.length} onClick={sources} title="For collections and concepts: add the source pages linked to them">
          + Sources
        </Button>
        <Button size="sm" variant="outline" disabled={!ids.length || busy} onClick={() => void citations()} title="Add papers that cite or are cited by the selection">
          + Citations
        </Button>
        <Button size="sm" variant="outline" disabled={!expansions.length} onClick={collapse} title="Take back the last expansion">
          Collapse
        </Button>
        <Button size="sm" variant="outline" disabled={ids.length !== 2 || busy} onClick={() => void path()} title="Select the shortest route between the two selected pages">
          Path between two
        </Button>
        <Button size="sm" variant="ghost" disabled={!ids.length} onClick={ctx.clearSelection}>
          Clear
        </Button>
      </div>
      <label className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Keep only type</span>
        <select
          className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2 text-sm disabled:opacity-50"
          aria-label="Keep only one type"
          disabled={types.length < 2}
          value=""
          onChange={(e) => e.target.value && ctx.select(onlyType(ids, ctx.byId, e.target.value))}
        >
          <option value="">{types.length < 2 ? "one type selected" : "choose a type…"}</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      {note && (
        <p className="text-xs text-muted-foreground" role="status">
          {note}
        </p>
      )}
      <p className="border-t pt-2 text-xs text-muted-foreground">
        Right-drag draws a box (Shift adds). Cmd/Ctrl + right-drag draws a lasso that adds.
      </p>
    </div>
  );
}
