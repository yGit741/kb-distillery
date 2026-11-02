---
type: paper
layer: source
title: "Fixture generalization bounds"
authors: [Jane Doe]
year: 2020
area: [learning-theory]
maturity: digested
depth: easy
raw: none
citekey:
url: https://example.org/papers/fixture-generalization-bounds
sources: [{resource: https://example.org/papers/fixture-generalization-bounds}]
recommended_by: [jane-doe]
discussed_with: []
aliases: [2020-fixture-generalization-bounds]
---

# Fixture generalization bounds

**Problem:** How large is the gap between train and test risk?

**Main result:** A uniform bound that scales with the square root of complexity over sample size.

## Setup & assumptions

IID samples, bounded loss.

## Proof idea (sketch only)

Symmetrization plus a union bound.

## Key equations

$R(h) \le \hat R(h) + \sqrt{C/n}$

## Takeaways for my thesis

- Baseline for [[generalization]].

## Links out
- Concepts: [[generalization]], [[pac-learning]]
- Person: [[jane-doe]]
