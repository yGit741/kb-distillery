import { registerTour } from "@/features/tour/tours";

/**
 * The knowledge-base tour: what this app loads and from where. The engine is code only; the content is one
 * `kbs/<id>/` folder (its own git repo) or a `--kb <path>` chosen at launch, its page types come from that folder's
 * kb.toml, its digest instructions and flags fall back to the explorer's defaults, and think is one shared
 * space beside every knowledge base. One idea per step; targets are real elements (aria-label, data-tour).
 */
const KBS = "/system?tab=kbs";

registerTour(
  "knowledge-base",
  [
    {
      target: '[data-tour="kb-badge"]',
      place: "bottom",
      title: "One engine, many knowledge bases",
      // source: src/kb_distillery/kbconfig.py (discovery, selection); app/KbBadge.tsx
      body: "The explorer is only the engine. The header names the **knowledge base** it was launched with, a plain folder with its own kb.toml, content and git history.",
    },
    {
      go: KBS,
      target: '[data-tour="kb-active"]',
      wait: 3000,
      place: "bottom",
      title: "Loaded from a local folder",
      // source: src/kb_distillery/services/kb.py (active); kbconfig.discover: kbs/<id>/ or --kb <path>
      body: "System → Knowledge bases shows the folder behind this app. It was found under kbs/ (the folder name is the id) or passed as a path, and **relaunching** with --kb picks another.",
    },
    {
      target: '[data-tour="kb-git"]',
      title: "Its own git repository",
      // source: kbconfig.KbConfig.git_root; ops/core.py commits with git -C <kb root>
      body: "When the folder has .git, every kb(…) commit and kb-x.y.z tag lands **there**, never in the explorer. The row shows the branch, the last snapshot tag and what is uncommitted.",
    },
    {
      target: '[data-tour="kb-types"]',
      title: "Types from kb.toml",
      // source: src/kb_distillery/core/types.py ([types] tables); core/schema.py keeps the historical names
      body: "Source, Collection and Concept are the explorer's three kinds. Which **page types** live inside them is this knowledge base's choice, declared in its kb.toml and colouring the graph legend.",
    },
    {
      target: '[data-tour="kb-think"]',
      title: "Think is shared",
      // source: kb_distillery.paths.THINK_PATH = kbs/think; git/guard.py _shared_think_guard; distill cites think:<note>
      body: "One think space sits beside every knowledge base, in its own repo. Agents are blocked from writing there, and a distilled page cites its note as **think:**name.md.",
    },
    {
      target: '[data-tour="kb-digest"]',
      title: "Digest instructions per knowledge base",
      // source: src/kb_distillery/core/digest.py (digest/focus.md, types.md; meta-defaults/digest fallback)
      body: "Ingest is identical everywhere; digest is one engine plus these instructions. A knowledge base's digest/ folder **overrides** the explorer's default focus and concept kinds.",
    },
    {
      target: '[data-tour="kb-meta"]',
      title: "Generic meta lives in the explorer",
      // source: kb_distillery.paths.meta_file; flags/registry.py FLAGS_SOURCE; meta-defaults/{flags.toml,templates,docs}
      body: "Flags, templates and the routed docs moved to the explorer's meta-defaults/. A knowledge base keeps only its own metadata and may **override** any of them in its meta/.",
    },
  ],
  "How this app loads a knowledge base: the folder, its git repo, its types, the shared think space, what it overrides.",
);

/**
 * Viewing other knowledge bases (flag kb-view): pick them on the graph, see one region each, read their pages.
 * They are read-only; every write stays on the knowledge base this app was launched with.
 */
registerTour(
  "kb-view",
  [
    {
      go: "/graph",
      target: '[data-tour="kb-badge"]',
      wait: 4000,
      place: "bottom",
      title: "Pick the knowledge bases",
      // source: app/KbBadge.tsx (KbMenu); GET /api/graph?kb=a,b (src/kb_distillery/api/routers/graph.py)
      body: "The name at the top left is a menu. Tick any knowledge base, or none. The choice goes into the link (**?kbs=**), so a presentation link opens the same view.",
    },
    {
      target: '[data-testid="graph-screen"]',
      title: "One region per knowledge base",
      // source: lab/kbRegions.ts (anchors, dashed outline, name above); services/graph.py merge_snapshots
      body: "Each sits in its own dashed **region**, named above it. Drag the name to move the whole region; colour still means page type.",
    },
    {
      target: '[data-testid="graph-screen"]',
      title: "Pages are view only",
      // source: features/pages/PageReader.tsx viewOnly; services/kbview.py (writes take no kb)
      body: "Double-click a node of another knowledge base to read it. Pin, Connect and Obsidian are hidden, since **edits** stay on this app's own knowledge base.",
    },
  ],
  "Pick knowledge bases from the header, add one from disk, read their pages view only.",
);
