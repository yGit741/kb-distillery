/** Casual sentences and the lines the rules parser must write for them (names as typed). */
export const SENTENCES: { text: string; lines: string[] }[] = [
  { text: "only non-orphans within 3 hops of Learning theory", lines: ['show nodes degree > 0 and within 3 hops of "Learning theory"'] },
  { text: "nodes that share a contradicts edge", lines: ["show nodes having edge contradicts"] },
  { text: "color by type", lines: ["style nodes color by type"] },
  { text: "thicken contradicts edges", lines: ["style edges width by thick for type contradicts"] },
  { text: "contradictions within 2 hops of favorites", lines: ["show nodes having edge contradicts and within 2 hops of favorites"] },
  { text: "what connects Learning theory and Compression", lines: ['show nodes paths between "Learning theory" and "Compression" up to 4 hops'] },
  { text: "hubs with no think note", lines: ["show nodes degree >= 8 and not linked_from type think"] },
  { text: "similar to this", lines: ['show nodes about "$focus"', 'show nodes name "$focus"'] },
  { text: "papers added this month with degree < 2", lines: ["show nodes type paper and created > 30d and degree < 2"] },
  { text: "leaves within 3 hops of Generalization", lines: ['show nodes degree = 1 and within 3 hops of "Generalization"'] },
  { text: "only supports edges, color by type", lines: ["show edges type supports", "style nodes color by type"] },
  { text: "hide mentions under 3", lines: ["hide edges type mentions and count < 3"] },
  { text: "favorites", lines: ["show nodes favorite"] },
];
