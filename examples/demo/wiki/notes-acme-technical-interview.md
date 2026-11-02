---
type: notes
layer: source
title: "Acme technical interview notes"
maturity: digested
depth: easy
raw: raw/printed-docs/acme-technical-interview-notes.md
company: Acme Robotics
created: 2026-10-15T00:00:00Z
stage: technical
related: [omer-shahar.md, interview-acme-technical.md, process-acme-robotics.md]
description: "Dana notes from the Acme technical interview with Omer Shahar on 15 October: tracker implementation, lidar-camera timestamp alignment, DataLoader performance, retraining triggers; strong on tracking, slower on time alignment."
generated: {by: human:dana-levi}
---

# Acme technical interview notes

**With:** [Omer Shahar](omer-shahar.md) · **Interview:** [Acme technical interview](interview-acme-technical.md) · **Company:** [Acme Robotics](company-acme-robotics.md)

**What it was about:** A 60 minute video interview with a staff perception engineer, mixing a coding exercise with design questions.

## Key claims
- Questions: a shipped-model post-mortem, a minimal multi-object tracker (Hungarian vs greedy matching), fusing detections with a 30 ms skew ([Sensor fusion](skill-sensor-fusion.md)), DataLoader slowdowns ([PyTorch](skill-pytorch.md)), and a retraining trigger for a new site ([ML-ops](skill-ml-ops.md)).
- Went well: tracker discussion, unprompted track birth and death thresholds, and the ML-ops answer built on [Gemini chat: Acme system-design and ML-ops prep](chat-gemini-acme-system-design-prep.md).
- To improve: propose IMU interpolation first for time alignment; revise Hungarian complexity.
- Omer will recommend the system-design round ([System design for ML](skill-system-design.md)); [Noa Peretz](noa-peretz.md) confirms the date.

## Takeaways
Positive outcome. Prepare the design round with the same chat material.

## Links out
- Concepts: [Omer Shahar](omer-shahar.md), [Acme technical interview](interview-acme-technical.md), [Sensor fusion](skill-sensor-fusion.md), [PyTorch](skill-pytorch.md), [ML-ops](skill-ml-ops.md), [System design for ML](skill-system-design.md)
