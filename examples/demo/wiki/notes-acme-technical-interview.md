---
type: notes
layer: source
status: digested
depth: easy
raw: raw/printed-docs/acme-technical-interview-notes.md
company: Acme Robotics
date: 2026-10-15
stage: technical
related: [omer-shahar, interview-acme-technical, process-acme-robotics]
summary: "Dana notes from the Acme technical interview with Omer Shahar on 15 October: tracker implementation, lidar-camera timestamp alignment, DataLoader performance, retraining triggers; strong on tracking, slower on time alignment."
summary_by: me
---

# Acme technical interview notes

**With:** [[omer-shahar]] · **Interview:** [[interview-acme-technical]] · **Company:** [[company-acme-robotics]]

**What it was about:** A 60 minute video interview with a staff perception engineer, mixing a coding exercise with design questions.

## Key claims
- Questions: a shipped-model post-mortem, a minimal multi-object tracker (Hungarian vs greedy matching), fusing detections with a 30 ms skew ([[skill-sensor-fusion]]), DataLoader slowdowns ([[skill-pytorch]]), and a retraining trigger for a new site ([[skill-ml-ops]]).
- Went well: tracker discussion, unprompted track birth and death thresholds, and the ML-ops answer built on [[chat-gemini-acme-system-design-prep]].
- To improve: propose IMU interpolation first for time alignment; revise Hungarian complexity.
- Omer will recommend the system-design round ([[skill-system-design]]); [[noa-peretz]] confirms the date.

## Takeaways
Positive outcome. Prepare the design round with the same chat material.

## Links out
- Concepts: [[omer-shahar]], [[interview-acme-technical]], [[skill-sensor-fusion]], [[skill-pytorch]], [[skill-ml-ops]], [[skill-system-design]]
