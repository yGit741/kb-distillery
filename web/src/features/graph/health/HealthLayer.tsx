import { useEffect } from "react";
import type { NeighborMap } from "../graphData";
import type { GNode } from "../types";
import { HealthDial } from "./HealthDial";
import { useHealth } from "./healthStore";
import { KindView } from "./KindView";

interface Props {
  nodes: readonly GNode[];
  neighbors: NeighborMap;
  byId: ReadonlyMap<string, GNode>;
  support: ReadonlyMap<string, number>;
  onRead: (id: string) => void;
}

/**
 * What the Health view adds over the map (flag knowledge-health): the dial of source kinds, or, once a kind is
 * pressed, the inside of that kind over the whole area. Leaving the Health view leaves the kind too.
 */
export function HealthLayer({ nodes, neighbors, byId, support, onRead }: Props) {
  const inside = useHealth((s) => s.inside);
  const leave = useHealth((s) => s.leave);
  useEffect(() => () => useHealth.getState().leave(), []);
  if (inside) return <KindView kind={inside} nodes={nodes} neighbors={neighbors} byId={byId} support={support} onRead={onRead} onClose={leave} />;
  return <HealthDial nodes={nodes} neighbors={neighbors} byId={byId} />;
}
