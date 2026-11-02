---
type: chat
layer: source
title: "Gemini chat: Acme system-design and ML-ops prep"
maturity: digested
depth: easy
raw: raw/llm-chats/gemini-acme-system-design-prep.md
company: Acme Robotics
created: 2026-10-12T00:00:00Z
stage: system-design prep
related: [skill-system-design.md, skill-ml-ops.md, skill-sensor-fusion.md, process-acme-robotics.md]
description: "Gemini prep chat on the Acme system-design round: structure of a perception design answer, an ML-ops checklist (golden sets, shadow deployment, drift monitors), how to present sensor fusion, and latency budgeting."
generated: {by: human:dana-levi}
---

# Gemini chat: Acme system-design and ML-ops prep

**Company:** [[company-acme-robotics]] · **Used for:** [[interview-acme-technical]] and the system-design round that follows.

**What it was about:** Dana asked what a warehouse-perception design question looks like. Gemini gave a seven-step answer structure and went deep on ML-ops and fusion.

## Key claims
- Likely prompts: design a detect-and-track pipeline for a robot fleet, or design the retraining loop ([[skill-system-design]]).
- [[skill-ml-ops]]: dataset versioning, a golden set per scenario, CI that blocks a model if pedestrian recall drops, shadow deployment, drift monitors, rollback. Retraining triggers: drift alert, new site, failure cluster.
- [[skill-sensor-fusion]]: time sync, per-sensor detector, fusion stage, tracker; failure modes are timestamp skew, calibration drift, a blind sensor.
- Fix the latency budget first (for example 50 ms), allocate it per stage, say what to quantize first.

## What worked
The shadow-deployment and golden-set points were reused in the technical interview ([[notes-acme-technical-interview]]).

## Links out
- Concepts: [[skill-system-design]], [[skill-ml-ops]], [[skill-sensor-fusion]], [[company-acme-robotics]]
