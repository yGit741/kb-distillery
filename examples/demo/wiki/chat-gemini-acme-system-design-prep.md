---
type: chat
layer: source
status: digested
depth: easy
raw: raw/llm-chats/gemini-acme-system-design-prep.md
company: Acme Robotics
date: 2026-10-12
stage: system-design prep
related: [skill-system-design, skill-ml-ops, skill-sensor-fusion, process-acme-robotics]
summary: "Gemini prep chat on the Acme system-design round: structure of a perception design answer, an ML-ops checklist (golden sets, shadow deployment, drift monitors), how to present sensor fusion, and latency budgeting."
summary_by: me
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
