import { useMemo } from "react";
import { CitationMap } from "./CitationMap";
import { useLayer } from "./layerStore";
import type { GraphToolContext } from "./tools";

/** The citation map tool's sheet: a click selects the paper in the main graph and opens its genealogy drawer. */
export function CitationMapSheet({ ctx }: { ctx: GraphToolContext }) {
  const isSource = useMemo(() => (id: string) => ctx.byId.get(id)?.layer === "source", [ctx.byId]);
  const papers = useMemo(() => [...ctx.byId.values()].filter((n) => n.type === "paper").map((n) => ({ id: n.id, title: n.title || n.id, depth: n.depth, year: n.year })), [ctx.byId]);
  return (
    <CitationMap
      isSource={isSource}
      papers={papers}
      onPick={(id) => {
        if (ctx.byId.has(id)) {
          ctx.select([id]);
          ctx.focus(id, false);
        }
        useLayer.getState().openDrawer({ kind: "genealogy", focus: id });
      }}
    />
  );
}
