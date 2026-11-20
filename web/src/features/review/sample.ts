import type { Hunk, IngestListItem } from "@/api";
import type { Card, Deck, Reach, ReachRel } from "./api";

/** The sample deck the tours play on (`?sample=1`): nothing here reaches the server or spends a model call. */
const hunk = (id: string, slug: string, op: string, before: string, after: string, tokens: string[][], extra: Partial<Hunk> = {}): Hunk => ({
  id, op_id: "op1", op, slug, kind: "prose", before, after, tokens, reason: "", sources: [], links_added: [], links_removed: [],
  at: 3, span: 1, klass: "claims", ...extra,
});

const card = (proposal: string, h: Hunk, rest: Partial<Card>): Card => ({
  id: `${proposal}:${h.id}`, proposal_id: proposal, hunk: h, klass: h.klass, tier: "review", page_title: h.slug,
  context_before: "", context_after: "", decision: null, findings: [], stale: false, group: `proposal:${proposal}`,
  producer: "chat", source: "", updated: "2026-11-17T08:00:00+00:00", ...rest,
});

const reach = (rows: [string, string, ReachRel, boolean?][], total = rows.length): Reach => ({
  total, pages: rows.map(([slug, title, rel, exists = true]) => ({ slug, title, rel, exists })),
});

/** The pages of the sample wiki the graph search can bring in. */
export const SAMPLE_PAGES: { slug: string; title: string }[] = [
  { slug: "sensor-fusion", title: "Sensor fusion" }, { slug: "radar", title: "Radar" }, { slug: "camera", title: "Camera" },
  { slug: "perception-latency", title: "Perception latency" }, { slug: "tracking", title: "Object tracking" },
  { slug: "hd-map", title: "HD map" }, { slug: "calibration", title: "Calibration" }, { slug: "lane-model", title: "Lane model" },
  { slug: "ego-motion", title: "Ego motion" }, { slug: "timing", title: "Sensor timing" }, { slug: "urban-scenes", title: "Urban scenes" },
];

/** The graph search on the sample deck: a word match on titles, no model, no server. */
export async function sampleSearch(text: string, exclude: string) {
  await new Promise((r) => setTimeout(r, 300));
  const cypher = /^\s*MATCH\b/i.test(text);
  const words = text.toLowerCase().split(/\W+/).filter((w) => w.length > 2);
  const pages = SAMPLE_PAGES.filter((p) => p.slug !== exclude && (cypher || words.some((w) => p.title.toLowerCase().includes(w) || p.slug.includes(w))));
  return {
    pages: pages.length || cypher ? pages : SAMPLE_PAGES.filter((p) => p.slug !== exclude).slice(0, 4),
    explanation: cypher ? "Sample: every page (Cypher isn't run on the sample deck)." : `Sample: pages whose title shares a word with "${text}".`,
    cypher: cypher ? text : "MATCH (p:Page) WHERE p.title CONTAINS $words RETURN p.slug",
  };
}

const NEW_PAGE = `---
type: Concept
title: Radar ghost targets
description: False radar detections from multipath reflections, and how fusion with the camera suppresses them.
sources:
  - id: radar-paper
    resource: /raw/radar-ghosts.pdf
---

# Radar ghost targets

A ghost target is a radar detection with no physical object behind it, usually a multipath reflection off a guard rail or a tunnel wall.[^radar-paper]

Camera confirmation removes most ghosts: a radar track that never gains a matching camera object within 300 ms is dropped.[^radar-paper]
`;

export const SAMPLE_DECK: Deck = {
  proposals: [
    { id: "s-ingest", title: "Ingest radar-ghosts.pdf", producer: "ingest", instruction: "ingest raw/radar-ghosts.pdf", source: "raw/radar-ghosts.pdf", stale: false, stale_pages: [], updated: "2026-11-17T08:05:00+00:00", hunks: 2, group: "source:raw/radar-ghosts.pdf" },
    { id: "s-chat", title: "Chat: soften the latency claim", producer: "chat", instruction: "soften the latency claim", source: "", stale: false, stale_pages: [], updated: "2026-11-17T08:00:00+00:00", hunks: 1, group: "proposal:s-chat" },
    { id: "s-lint", title: "Nightly lint: link fixes", producer: "lint", instruction: "", source: "", stale: false, stale_pages: [], updated: "2026-11-17T07:00:00+00:00", hunks: 3, group: "proposal:s-lint" },
  ],
  cards: [
    card("s-ingest", hunk("n1", "radar-ghost-targets", "create_page", "", NEW_PAGE, [["insert", NEW_PAGE]], { kind: "structure", klass: "new_page", at: 0, span: 0, reason: "digest of the new source", sources: ["radar-paper"] }), {
      page_title: "Radar ghost targets", producer: "ingest", source: "raw/radar-ghosts.pdf", group: "source:raw/radar-ghosts.pdf", updated: "2026-11-17T08:05:00+00:00",
      reach: reach([["sensor-fusion", "Sensor fusion", "in", true], ["radar", "Radar", "out"], ["camera", "Camera", "out"]]),
    }),
    card("s-ingest", hunk("n2", "sensor-fusion", "edit_page",
      "Fusion combines radar range with camera classification.\n\n",
      "Fusion combines radar range with camera classification, and drops radar tracks the camera never confirms ([ghost targets](/radar-ghost-targets.md)).\n\n",
      [["equal", "Fusion combines radar range with camera classification"], ["delete", "."], ["insert", ", and drops radar tracks the camera never confirms ([ghost targets](/radar-ghost-targets.md))."], ["equal", "\n\n"]],
      { kind: "structure", links_added: ["radar-ghost-targets"], reason: "link the new page from where fusion is explained", sources: ["radar-paper"] }), {
      page_title: "Sensor fusion", producer: "ingest", source: "raw/radar-ghosts.pdf", group: "source:raw/radar-ghosts.pdf", updated: "2026-11-17T08:05:00+00:00",
      context_before: "# Sensor fusion", context_after: "## Timing\n\nEach sensor runs on its own clock; fusion aligns them by timestamp.",
      reach: reach([["radar-ghost-targets", "Radar ghost targets", "added", false], ["perception-latency", "Perception latency", "in"], ["tracking", "Object tracking", "in"],
        ["urban-scenes", "Urban scenes", "in"], ["radar", "Radar", "out"], ["camera", "Camera", "out"], ["timing", "Sensor timing", "out"]]),
    }),
    card("s-chat", hunk("c1", "perception-latency", "edit_page",
      "The perception stack always reacts within 50 ms.\n\n",
      "The perception stack reacts within 50 ms in most highway scenes; dense urban scenes can take up to 80 ms.\n\n",
      [["equal", "The perception stack "], ["delete", "always reacts within 50 ms"], ["insert", "reacts within 50 ms in most highway scenes; dense urban scenes can take up to 80 ms"], ["equal", ".\n\n"]],
      { reason: "the measured p95 is higher in urban scenes", sources: ["latency-report"] }), {
      page_title: "Perception latency", context_before: "# Perception latency", context_after: "Latency is measured from frame capture to the fused object list.",
      reach: reach([["sensor-fusion", "Sensor fusion", "in"], ["tracking", "Object tracking", "in"], ["urban-scenes", "Urban scenes", "out"], ["timing", "Sensor timing", "out"]]),
    }),
    ...["l1", "l2", "l3"].map((id, i) => card("s-lint", hunk(id, ["calibration", "lane-model", "ego-motion"][i]!, "rewrite_link",
      "See [the old map](/hd-map-v1.md).", "See [the map](/hd-map.md).",
      [["equal", "See ["], ["delete", "the old map](/hd-map-v1.md)"], ["insert", "the map](/hd-map.md)"], ["equal", "."]],
      { kind: "structure", klass: "links", reason: "hd-map-v1 was merged into hd-map" }), { producer: "lint", page_title: ["Calibration", "Lane model", "Ego motion"][i]!, tier: "auto_apply",
        reach: reach([["hd-map", "HD map", "added"], ["hd-map-v1", "HD map v1", "removed", false]]) })),
  ],
};

const job = (id: string, source: string, rest: Partial<IngestListItem>): IngestListItem => ({
  id, status: "done", source, tier: "full", collection: "", steps: [], proposal_id: null, pages: [], error: null, kind: "file",
  started: 0, finished: null, backend: "", step: "", proposal_status: null, proposal_updated: null, ...rest,
});
const STEPS = (active: number) => ["fetch", "convert", "digest", "propose"].map((name, i) => ({ name, state: i < active ? "done" : i === active ? "active" : "pending", detail: "" }));

/** The sample queue: one source reading, one waiting for review (the cards above), one failed, one applied. */
export const SAMPLE_JOBS: IngestListItem[] = [
  job("j-run", "https://arxiv.org/abs/2611.01234", { status: "running", kind: "url", steps: STEPS(2), step: "digest" }),
  job("j-radar", "raw/radar-ghosts.pdf", { proposal_id: "s-ingest", proposal_status: "open", pages: ["radar-ghost-targets", "sensor-fusion"] }),
  job("j-fail", "scanned-notes.pdf", { status: "failed", error: "couldn't read the file", steps: STEPS(1) }),
  job("j-old", "raw/lane-detection-survey.pdf", { proposal_id: "s-old", proposal_status: "applied", pages: ["lane-model"] }),
];

/** What a rewrite of the sample latency card returns: the card comes back as v2. */
export const SAMPLE_REWRITE = {
  reply: "Shortened it and kept the urban number.",
  after: "The perception stack reacts within 50 ms on highways and up to 80 ms in dense urban scenes.\n\n",
  tokens: [["equal", "The perception stack "], ["delete", "always reacts within 50 ms"], ["insert", "reacts within 50 ms on highways and up to 80 ms in dense urban scenes"], ["equal", ".\n\n"]],
};

/** `?sample=1` as the router parses it (a number) or as typed (a string). */
export const isSample = (search: Record<string, unknown>): boolean => String(search["sample"] ?? "") === "1";
