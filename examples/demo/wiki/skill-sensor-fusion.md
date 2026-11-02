---
type: skill
layer: concept
maturity: growing
sources: [{resource: posting-acme-senior-ml-engineer.md}, {resource: notes-acme-technical-interview.md}, {resource: chat-gemini-acme-system-design-prep.md}]
related: [role-senior-ml-engineer-acme.md, interview-acme-technical.md, skill-system-design.md, omer-shahar.md]
description: "Sensor fusion of lidar, camera and IMU for tracking at Acme Robotics; the interview weak spot was timestamp alignment, fixed by interpolating IMU first."
generated: {by: human:dana-levi}
---

# Sensor fusion

Combining lidar, camera and IMU into one state estimate: time sync, per-sensor detection, a fusion stage (Kalman filter or learned) and a tracker.

## Evidence
- Central to [Senior ML Engineer, Perception (Acme)](role-senior-ml-engineer-acme.md).
- [Acme technical interview](interview-acme-technical.md): 30 ms skew question; improvement noted in [Acme technical interview notes](notes-acme-technical-interview.md).
- Failure modes in [Gemini chat: Acme system-design and ML-ops prep](chat-gemini-acme-system-design-prep.md).

Pairs with [System design for ML](skill-system-design.md).
