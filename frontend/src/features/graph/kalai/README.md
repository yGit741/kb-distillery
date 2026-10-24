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

## Open questions to decide together

1. Which of the three earns a permanent place (graduate = drop the flag), and where: toolbar tool, a
   view in the label rail, or the nightly report?
2. Spectrum: add level-3 lists (which triples), or a "thesis candidate" card that joins a gap pair with
   the q- pages near it?
3. Noise: should "drop sources" use the real source → concept evidence (needs the API to expose which
   sources back a concept link)?
4. Thresholds: per-theme bridge across *all* draws (most frequent pivotal link) instead of draw 0.
