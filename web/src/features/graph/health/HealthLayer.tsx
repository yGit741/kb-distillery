import type { NeighborMap } from "../graphData";
import type { GNode } from "../types";
import { HealthDial } from "./HealthDial";

interface Props {
  nodes: readonly GNode[];
  neighbors: NeighborMap;
  byId: ReadonlyMap<string, GNode>;
}

/** What the Health view adds over the map (flag knowledge-health): the dial of source kinds. */
export function HealthLayer({ nodes, neighbors, byId }: Props) {
  // its own container, so the dial can fold its names away when the graph's area is narrow (a split pane, an open page)
  return (
    <div className="pointer-events-none absolute inset-0 @container">
      <HealthDial nodes={nodes} neighbors={neighbors} byId={byId} />
    </div>
  );
}
