# Directions toolkit (graph experiments)

Analyses of the vault graph, behind the feature flag `research-tools` (`kits/base/defaults/flags.toml`,
runtime, off by default) and, inside it, one **experiment switch** each. With the flag on, the toolbar's
flask button (**Experiments**) switches them, or `?exp=fourier,noise,threshold,directions` on the graph URL.
Switches live in this browser only (`kb-graph-experiments-v1`). Everything runs in the browser on the graph
snapshot: no API change, works on the share site.

| Switch | Tool | Module | Panel |
|--------|------|--------|-------|
| `fourier` | Theme spectrum (Σ) | `fourier.ts` | `FourierPanel.tsx` |
| `noise` | Noise stability (waves) | `noise.ts` | `NoisePanel.tsx` |
| `threshold` | Sharp thresholds (pulse) | `threshold.ts` | `ThresholdPanel.tsx` |
| `directions` | Research directions (compass) | `directions.ts` | `DirectionsPanel.tsx` |

Shared: `core.ts` (seeded RNG, page graph, Louvain, PageRank, union-find), `ui.tsx` (result cache, chips,
mini chart). Generic hooks other tools can reuse: `../tools/experiments.ts` (switches; a tool sets
`flag: "<id>"`), a tool's `featureFlag` (`@/flags`) and `../tools/decor.ts` (halos per page, fade per link,
one owner at a time). `register.tsx` is the only place that registers them.

## What each one answers

- **Theme spectrum.** Which themes the notes combine, which big ones never meet, and what predicts deep
  reading. Each themed page is x in {0,1}^k; the expansion is in p-biased characters, so it measures
  structure beyond theme frequency. Level-2 coefficient = correlation of two themes; level-k energy is
  compared with a shuffled vault; the attention signal f = ±1 (read in depth or not) gives which themes and
  pairs predict deep reading. "Holes" = three themes that meet in every pair but never all together,
  against the Kirkwood estimate n·p_ab·p_bc·p_ac / (p_a·p_b·p_c) built from the pairs alone.
- **Noise stability.** Whether "these ideas belong together" or "this concept is central" survives if some
  sources or links had been missed. Drop ε of sources or links, re-run Louvain + PageRank 10 times; halo =
  page whose cluster changes (Jaccard < 0.6); "central, but not for sure" = top concepts that fall out of
  the top 20.
- **Sharp thresholds.** At what link density a theme holds together and which pages tip it. Keep each link
  with probability p (one coupled draw drives the slider, 120 draws drive the curves); property = one piece
  holds half the theme's pages. p50 = where it holds half the time, width = p90 − p10, hinge = the page most
  often on the tipping link. Influence (`influence.ts`): a page is pivotal for a theme when, in a random kept
  graph at the theme's p50, the theme holds with the page and falls apart without it.
- **Research directions.** `directions.ts` turns the spectrum's gaps and holes into cards: sides (pages, read
  in depth), existing pages in the intersection vs expected, the closest `q-` questions and ideas (closeness
  to a theme = share of the page and its neighbours carrying it; a page ranks by its weakest side), and a
  foothold: strong (reach ≥ 0.3), thin, or greenfield.

## Open questions

1. Which of the analyses earns a permanent place (graduate = drop the flag), and where: toolbar tool, a
   view in the label rail, or the nightly report?
2. Noise: should "drop sources" use the real source → concept evidence (needs the API to expose which
   sources back a concept link)?
3. Influence as a size/colour mode of the whole graph (needs a metric hook in style.ts), not only halos?
