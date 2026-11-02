---
type: skill
layer: concept
title: "Sensor fusion"
maturity: growing
sources: [{resource: posting-acme-senior-ml-engineer.md}, {resource: notes-acme-technical-interview.md}, {resource: chat-gemini-acme-system-design-prep.md}]
related: [role-senior-ml-engineer-acme.md, interview-acme-technical.md, skill-system-design.md, omer-shahar.md]
description: "Sensor fusion of lidar, camera and IMU for tracking at Acme Robotics; the interview weak spot was timestamp alignment, fixed by interpolating IMU first."
generated: {by: human:dana-levi}
---

# Sensor fusion

Combining lidar, camera and IMU into one state estimate: time sync, per-sensor detection, a fusion stage (Kalman filter or learned) and a tracker.

## Evidence
- Central to [[role-senior-ml-engineer-acme]].
- [[interview-acme-technical]]: 30 ms skew question; improvement noted in [[notes-acme-technical-interview]].
- Failure modes in [[chat-gemini-acme-system-design-prep]].

Pairs with [[skill-system-design]].
