# Graph label rail (ported from the Label Lab)

The left rail of the graph page. It decides which pages get a label, how big each label is, and where it goes.
It also holds the saved views (user stories). It started as a Claude artifact experiment on the real vault
graph and was moved here as-is, to be refined later.

| Module | What it does |
|---|---|
| `config.ts` | every knob (`LabConfig`) and its research-backed default; type tiers and depth weights |
| `importance.ts` | the importance score (see below); PageRank, Brandes betweenness, hops from the selection |
| `labelPlan.ts` | the planner: candidates, budget, forced labels, focus, placement with declutter; label text and size |
| `regions.ts` | theme regions (median of each area's pages) and core hulls |
| `draw.ts` | canvas drawing in CSS px: region names, labels with fades, the hover lens, hulls under the nodes |
| `views.ts` | the saved views: each user story's knobs, colour, size, layout, drawn types and "Aa" types |
| `LabRail.tsx` | the rail UI, the "Why this rank" breakdown and the live readouts |

The importance score combines these signals:
- type tier
- digested evidence, weighted by reading depth (for collections, the mean depth of their members)
- link count
- PageRank
- betweenness
- open question
- thin spot
- orphan

Each signal is normalised within its type when the type has at least 5 drawn pages, and globally otherwise.

## Principles (hold in every view; they set the defaults)

- **Coverage budget:** about 12% of the canvas, roughly 20–40 labels at fit zoom (Bobák et al. 2024; Woodruff et al. 1998).
- **Growth with zoom:** zoom^0.5, Töpfer's radical law.
- **Panning never changes the label set:** labels are chosen for the whole graph (Been, Daiches & Yap 2006). A shown label gets a hysteresis bonus and keeps its offset, and labels fade over 250 ms.
- **Ranking:** by degree of interest, importance minus distance from the focus (Furnas 1986; van Ham & Perer 2009). Never by raw degree.
- **Typography:** three discrete label tiers, never below 11 px, with a halo.
- **Placement:** try above the node first, then below, right, left.
- **Grouping:** themes as regions and hulls; a hover lens of at most 20 labels (Fekete & Plaisant 1999); a selection's neighbourhood capped at about 20.

The two research reports and the measurements behind these numbers are in the artifact's Principles and User
stories tabs.

## Not yet

- A recency signal and the "What changed" view, which need an `edited` date from the graph API.
- Coherence conflicts as edges.
- Refining the rail's look and its default sections.
