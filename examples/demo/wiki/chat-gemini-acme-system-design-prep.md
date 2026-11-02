---
type: chat
layer: source
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

**Company:** [Acme Robotics](company-acme-robotics.md) · **Used for:** [Acme technical interview](interview-acme-technical.md) and the system-design round that follows.

**What it was about:** Dana asked what a warehouse-perception design question looks like. Gemini gave a seven-step answer structure and went deep on ML-ops and fusion.

## Key claims
- Likely prompts: design a detect-and-track pipeline for a robot fleet, or design the retraining loop ([System design for ML](skill-system-design.md)).
- [ML-ops](skill-ml-ops.md): dataset versioning, a golden set per scenario, CI that blocks a model if pedestrian recall drops, shadow deployment, drift monitors, rollback. Retraining triggers: drift alert, new site, failure cluster.
- [Sensor fusion](skill-sensor-fusion.md): time sync, per-sensor detector, fusion stage, tracker; failure modes are timestamp skew, calibration drift, a blind sensor.
- Fix the latency budget first (for example 50 ms), allocate it per stage, say what to quantize first.

## What worked
The shadow-deployment and golden-set points were reused in the technical interview ([Acme technical interview notes](notes-acme-technical-interview.md)).

## Links out
- Concepts: [System design for ML](skill-system-design.md), [ML-ops](skill-ml-ops.md), [Sensor fusion](skill-sensor-fusion.md), [Acme Robotics](company-acme-robotics.md)
