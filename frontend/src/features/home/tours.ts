import { useGraphUi } from "@/features/graph/store";
import { registerTour, type TourStep } from "@/features/tour/tours";
import { useKb } from "@/lib/store";

/**
 * The Home → Graph journeys: each tour tells one story a first-time reader can follow, starting on Home,
 * crossing into the full graph and coming back. Written in the owner's voice; one idea per step, body ≤ 2
 * sentences, and every sentence is backed by the page or code the `// source:` line above it names.
 * Blocks (B1 … B9) are shared between tours and return steps. Targets are real elements (`aria-label`,
 * `data-tour`, the views bar id); a step with `go` moves the app there first.
 */

const INTRO = '[aria-labelledby="home-intro"]';
/** the inner card: Pick a Concept, its ego graph and the pipeline strip */
const PICKER = '[data-tour="home-start"]';
const PIPELINE = '[data-tour="home-pipeline"]';
const VIEWS = "#graph-views";
/** pills in the views bar, in HEADLINE_STORIES order */
const PILL = (n: 1 | 2 | 3) => `${VIEWS} > button:nth-of-type(${n})`;
const SIGMA = `${VIEWS} button[aria-label^="Theme spectrum"]`;
const SELECTION = '[data-tour="graph-selection"]';
const DIRECTIONS = 'section[aria-label="Research directions"]';
/** the Directions panel computes the spectrum before it renders cards */
const SLOW = 8000;

// ---- pages the stories visit (wiki slugs)
const ALEXANDER_2025 = "paper-2025-do-neural-networks-need-gradient-descent-to-generalize";
const VOLUME = "volume-hypothesis";
const TOTAL_INFLUENCE = "total-influence";
const PARITY = "parity-function";
const ODONNELL = "book-2014-analysis-of-boolean-functions";

const go = (path: string, from = true) => (from ? `${path}&from=home` : path);

// ---- blocks
/** B1: what this vault is */
const welcome = (): TourStep => ({
  target: INTRO,
  place: "bottom",
  title: "What you are looking at",
  // source: AGENTS.md (Karpathy LLM-wiki pattern, agent-owned wiki/ over user-owned raw/); features/home/glossary.tsx (Raw → Source → Concept)
  body: "Every paper, lecture and blog post I read is distilled by an agent into linked notes, in the pattern of Karpathy's LLM wiki. The strip below shows how a raw file becomes a source and then concepts.",
});

/** B2: the picker's ego graph is one slice of the graph */
const subgraphCard = (): TourStep => ({
  target: PICKER,
  place: "bottom",
  title: "Pick a concept",
  // source: features/home/ConceptExplorer.tsx (egoSample: the concept's neighbourhood of the same graph snapshot; the shuffle draws another concept)
  body: "This mini graph is the real data, not an illustration: one concept and the pages linked to it, as you will meet them in the full graph. The shuffle picks another concept.",
});
const conceptCard = (): TourStep => ({
  target: PIPELINE,
  place: "top",
  title: "One source behind it",
  // source: features/home/samplers.ts (pickSource: full/deep first, then easy, then listed; PipelineStrip: Raw → Source → Concepts it feeds)
  body: "Next to the graph is one source the concept relies on, followed from the raw file to the page and on to every concept it feeds. Questions are mine to answer; ideas are what they rest on.",
});

/** B3: into the full graph, landing in the Map view on a page */
const dive = (slug: string): TourStep => ({
  target: VIEWS,
  go: go(`/graph?view=map&focus=${slug}`),
  wait: 4000,
  place: "bottom",
  title: "The full graph",
  // source: features/graph/lab/views.ts (Map: colorBy area, "themes on a ring, digested sources only"); features/graph/Legend.tsx
  body: "Same colours as the cards, one per theme (the legend runs along the bottom), and this bar switches between views. The ring you see is Map, the whole vault at a glance.",
});

/** B4: the Map view */
const mapView = (): TourStep => ({
  target: PILL(1),
  place: "bottom",
  title: "Map: what is in the vault",
  // source: features/graph/lab/views.ts (Map story: themes on a ring, ideas and questions inside, only digested sources; hulls: true)
  body: "Themes sit on a ring, their ideas and questions inside, and only the sources I actually digested are drawn. Hulls mark where a theme's pages cluster.",
});
const sigma = (): TourStep => ({
  target: SIGMA,
  place: "bottom",
  before: () => {
    const b = document.querySelector<HTMLButtonElement>(SIGMA);
    if (b && b.getAttribute("aria-pressed") !== "true") b.click();
  },
  title: "Σ: which themes my notes combine",
  // source: features/graph/views/ViewsBar.tsx (spectrumArcs: solid = positive coefficient, dashed = big pairs below chance); book-2014-analysis-of-boolean-functions.md (Fourier expansion as the book's first key concept)
  body: "Solid chords join themes that share pages more often than chance; dashed chords are big pairs that meet less than chance. Watch for the chord between Boolean analysis and Fourier analysis, the pair my notes treat together most.",
});

/** B5: the Thesis view */
const thesisView = (): TourStep => ({
  target: PILL(2),
  go: go("/graph?view=thesis"),
  wait: 4000,
  place: "bottom",
  title: "Thesis: the spine",
  // source: features/graph/lab/views.ts (THESIS_SEED: three themes, four questions, concepts, papers, the book, gil-kalai; story "one hop around it")
  body: "The direction I am weighing — generalization of over-parameterized networks, met through Boolean analysis — as a seed of themes, open questions, concepts and papers, with one hop around it. Everything else is hidden.",
});

/** B6: the Explore view and its Research directions panel */
const exploreView = (): TourStep => ({
  target: DIRECTIONS,
  go: go("/graph?view=explore"),
  wait: SLOW,
  place: "right",
  title: "Explore: where a thesis could sit",
  // source: features/graph/kalai/directions.ts (gaps = two big themes that rarely share a page, holes = three themes meeting only in pairs; footholdOf: strong = reach ≥ 0.3 of my own questions/ideas to every side)
  body: "Each card is an intersection my vault leaves empty: two big themes that rarely share a page, or three that only meet in pairs. A strong foothold means my own questions and ideas already reach every side of it.",
});

/** B7: touch one page — focus and select it, then explain it */
const touch = (slug: string, title: string, body: string): TourStep => ({
  target: SELECTION,
  before: () => {
    useGraphUi.setState({ readerSlug: null, detailsOpen: false });
    useGraphUi.getState().requestFocus(slug);
    useKb.getState().setSelection([slug]);
  },
  place: "top",
  title,
  body,
});

/** B9: back on Home, with what the tour left unseen */
const homeAgain = (body: string, title = "What I left for you"): TourStep => ({
  target: INTRO,
  go: "/",
  place: "bottom",
  title,
  body,
});

// ---- the tours
registerTour(
  "first-visit",
  [
    welcome(),
    subgraphCard(),
    dive(TOTAL_INFLUENCE),
    mapView(),
    sigma(),
    touch(
      TOTAL_INFLUENCE,
      "Where Kalai meets transformers",
      // source: wiki/total-influence.md (one-liner; shared by three threads: Benjamini–Kalai–Schramm noise sensitivity, Hahn & Rofin's average sensitivity for transformers, sharp thresholds via Margulis–Russo)
      "Total influence: how many coordinates, on average, can flip a Boolean function's output. The same quantity runs through Kalai's work on noise sensitivity and sharp thresholds and through Hahn & Rofin's explanation of why transformers struggle with sensitive functions like parity — which is why this node sits between those threads.",
    ),
    homeAgain(
      // source: features/graph/views/ViewsBar.tsx (Thesis and Explore pills, ⓘ "How this view is computed"); features/graph/SideReader.tsx (double-click opens the reader)
      "Play around and let me know what you think — it's still a work in progress, and I'm open to feedback. Try the Thesis and Explore views, the ⓘ next to each view, and double-click any node to read it.",
      "Play around",
    ),
  ],
  "What is in this vault, in 90 seconds",
);

registerTour(
  "thesis-story",
  [
    welcome(),
    conceptCard(),
    dive(VOLUME),
    thesisView(),
    touch(
      VOLUME,
      "The volume hypothesis",
      // source: wiki/volume-hypothesis.md (one-liner; Intuition: credit to the architecture and the prior, not the optimizer)
      "Among the weight settings that fit the training data, the ones that generalize well occupy far more prior mass than the ones that generalize badly. If so, any optimizer that fits the data — even guessing weights at random until one fits — generalizes about as well as gradient descent.",
    ),
    touch(
      ALEXANDER_2025,
      "Alexander 2025: the test case",
      // source: wiki/paper-2025-do-neural-networks-need-gradient-descent-to-generalize.md (Main result: G&C deteriorates with width, Theorem 1; improves with depth, Theorem 2; builds on paper-2019-implicit-regularization-in-deep-matrix-factorization, linked twice)
      "Sampling weights at random until one fits generalizes better as depth grows and worse as width grows, so width and depth pull the volume in opposite directions. It is the test case for the volume hypothesis, in the deep matrix factorizations of the 2019 implicit-regularization paper lit beside it.",
    ),
    exploreView(),
    homeAgain(
      // source: features/graph/views/ViewsBar.tsx (Σ, ⓘ); wiki/q-does-the-gradient-variance-bound-explain-the-sparse-parity-s.md (open question, spawned from paper-2017-failures-of-gradient-based-deep-learning)
      "I left the Σ chords in Map, the other direction cards, the ⓘ behind each view, and my open question on whether the gradient-variance bound explains how SGD still learns sparse parities.",
    ),
  ],
  "Why over-parameterized networks generalize — the question I am chasing",
  { menu: false },
);

registerTour(
  "boolean-bridge",
  [
    welcome(),
    dive(PARITY),
    sigma(),
    thesisView(),
    touch(
      PARITY,
      "Parity: the canonical hard function",
      // source: wiki/parity-function.md (all Fourier mass on level |S|; low-degree learners see zero signal; Connections: paper-2017 gradient variance ≤ G(w)²/2^d); wiki/q-does-the-gradient-variance-bound-explain-the-sparse-parity-s.md
      "The XOR of a subset of bits has all its Fourier mass on one level, so a learner that only sees low-degree correlations sees exactly zero signal, and gradient variance over random parities is exponentially small. My open question: does that bound explain the staircase results where SGD still learns k-sparse parities?",
    ),
    touch(
      ODONNELL,
      "O'Donnell's book, and Fourier degree",
      // source: wiki/book-2014-analysis-of-boolean-functions.md (Key concepts: Fourier expansion, influence, noise stability and hypercontractivity, low-degree learning); wiki/fourier-degree.md (learnability via low-degree concentration; "the most promising bridge in this vault"; open question vs spectral bias)
      "Analysis of Boolean Functions is where the vocabulary comes from: Fourier expansion, influence, noise stability and hypercontractivity, low-degree learning. Fourier degree is the bridge I am betting on — low-degree concentration is what makes a class learnable, and whether that is the same claim as spectral bias is an open question of mine.",
    ),
    homeAgain(
      // source: wiki/noise-stability.md, wiki/gil-kalai.md (both in THESIS_SEED); features/graph/lab/views.ts (Explore)
      "Still unseen: noise stability (the Kalai side of the bridge), Gil Kalai's blog as a hub of its own, and the Explore view where these themes meet or fail to.",
    ),
  ],
  "Where Boolean analysis meets learning theory in my notes",
  { menu: false },
);
