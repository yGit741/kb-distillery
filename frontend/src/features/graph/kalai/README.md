# Kalai toolkit (graph experiments)

Three analyses of the vault graph, each behind its own **experiment flag**. Turn them on in the
toolbar's flask button (**Experiments**), or with `?exp=fourier,noise,threshold` on the graph URL.
Switches live in this browser only (`kb-graph-experiments-v1`); nothing changes for anyone who did not
opt in. Everything runs in the browser on the graph snapshot: no API change, works on the share site.

| Flag | Tool | Module | Panel |
|------|------|--------|-------|
| `fourier` | Theme spectrum (Σ) | `fourier.ts` | `FourierPanel.tsx` |
| `noise` | Noise stability (waves) | `noise.ts` | `NoisePanel.tsx` |
| `threshold` | Sharp thresholds (pulse) | `threshold.ts` | `ThresholdPanel.tsx` |

Shared: `core.ts` (seeded RNG, page graph, Louvain, PageRank, union-find), `ui.tsx` (result cache, chips,
mini chart). Generic hooks other tools can reuse: `../tools/experiments.ts` (flags; a tool sets
`flag: "<id>"`) and `../tools/decor.ts` (halos per page, fade per link, one owner at a time).

## User stories

- **Theme spectrum.** When I choose where to dig, I want to see which themes my notes combine, which big
  ones never meet, and what predicts my deep reading, so that I can spot a thesis at an unexplored
  intersection. Each themed page is x in {0,1}^k; the expansion is in p-biased characters, so it measures
  structure beyond theme frequency. Level-2 coefficient = correlation of two themes; level-k energy is
  compared with a shuffled vault; the attention signal f = ±1 (read in depth or not) gives which themes
  and pairs predict deep reading.
- **Noise stability.** Before I rely on "these ideas belong together" or "this concept is central", I
  want to know whether that survives if I had missed some papers or links. Drop ε of sources or links,
  re-run Louvain + PageRank 10 times; halo = page whose cluster changes (Jaccard < 0.6); "central, but not
  for sure" = top concepts that fall out of the top 20.
- **Sharp thresholds.** When I want to know how well a theme is woven in, I want to see at what link
  density it holds together and which single link tips it. Keep each link with probability p (one coupled
  draw drives the slider, 120 draws drive the curves); property = one piece holds half the theme's pages.
  p50 = where it holds half the time, width = p90 − p10, bridge = the link that tipped it in draw 0.

## Findings on the vault (2026-10-24, 1136 pages, 473 themed)

- Pair structure is ×6.9 chance, triples ×1.6: the vault is pairwise. Over-represented: boolean-analysis
  × fourier-analysis (36 pages vs 13.9 expected). Gaps: learning-theory × quantum (1 vs 25),
  boolean-analysis × implicit-regularization (4 vs 28), implicit-regularization × quantum (0 vs 22).
- Deep reading: implicit-regularization pages 42% vs a 25% baseline; quantum 7%, optimization-theory 6%.
- Noise (15% of sources dropped): clusters keep mean Jaccard 0.69; the top-20 concepts are stable (99%).
  Fragile: the optimizer cluster (adamw, muon, nesterov, newton-schulz: 0.21), which rests on one source.
- Thresholds: most themes cohere at p ≈ 0.08–0.11; statistics 0.24 and quantum 0.36 (wide), held
  together through gil-kalai and the "why quantum computers cannot work" post. Theme pairs add nothing
  beyond the weaker theme's own cohesion: integration is limited by weak themes, not by missing bridges.

## Round 2 (2026-10-24): influence, hinges, holes

- **Influence (`influence.ts`, Thresholds panel → "Measure influence").** KKL: a page is pivotal for a
  theme when, in a random kept graph at the theme's p50, the theme holds with the page and falls apart
  without it; influence = Pr[pivotal], total = sum over themes (8 draws per theme, ~1.5 s). Halos can show
  pivotal pages instead of hinges. On the vault: gil-kalai 2.50 (pivotal for statistics 75%, quantum
  63%), then implicit-bias-of-gradient-descent and q-why-do-overparameterized-networks-generalize 1.13.
- **Hinges replace the draw-0 bridge.** The most frequent single tipping *link* appears in only 2–6% of
  draws: there is no one bridge link. Its *pages* are stable, so each theme now reports its hinge page and
  how often it sits on the tipping link: quantum → gil-kalai 79%, statistics → gil-kalai 57%; the
  well-woven themes have weak hinges (8–27%).
- **Holes (Theme spectrum → "Holes").** Three themes that meet in every pair but never all together,
  against the Kirkwood estimate n·p_ab·p_bc·p_ac / (p_a·p_b·p_c) built from the pairs alone. On the vault
  there is exactly one: implicit-regularization · learning-theory · optimization-theory (pairs 21, 9, 6
  pages; 0 with all three; 1.2 expected). It answers simplicial holes without a clique complex over the
  1 100 pages.

## Round 3 (2026-10-24): Research directions (flag `directions`, compass button)

Story: when I choose my thesis topic, I want the empty intersections of my vault as cards, each with what
already sits there and my closest questions and ideas, so that I can shortlist directions with evidence.
`directions.ts` turns the spectrum's gaps and holes into cards: sides (pages, read in depth), existing
pages in the intersection vs expected, the closest `q-` questions and ideas (closeness to a theme = share
of the page and its neighbours carrying it; a page ranks by its weakest side), and a foothold: strong
(reach ≥ 0.3), thin, or greenfield.

On the vault: 7 directions, 1 with a strong foothold — boolean-analysis × implicit-regularization (4 pages
vs 30 expected), reached by the Ising-perceptron / sharp-threshold questions and the volume hypothesis.
The quantum gaps are thin (reach ≤ 0.15) with 7 of 99 quantum pages read in depth: new ground, cold start.

## Open questions to decide together

1. Which of the analyses earns a permanent place (graduate = drop the flag), and where: toolbar tool, a
   view in the label rail, or the nightly report?
2. Spectrum: a "thesis candidate" card that joins a gap pair or the hole with the q- pages near it?
3. Noise: should "drop sources" use the real source → concept evidence (needs the API to expose which
   sources back a concept link)?
4. Influence as a size/colour mode of the whole graph (needs a metric hook in style.ts), not only halos?
