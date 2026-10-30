---
type: skill
layer: concept
status: growing
sources: [posting-acme-senior-ml-engineer, notes-acme-technical-interview, chat-gemini-acme-system-design-prep]
related: [role-senior-ml-engineer-acme, interview-acme-technical, skill-system-design, omer-shahar]
summary: "Sensor fusion of lidar, camera and IMU for tracking at Acme Robotics; the interview weak spot was timestamp alignment, fixed by interpolating IMU first."
summary_by: me
---

# Sensor fusion

Combining lidar, camera and IMU into one state estimate: time sync, per-sensor detection, a fusion stage (Kalman filter or learned) and a tracker.

## Evidence
- Central to [[role-senior-ml-engineer-acme]].
- [[interview-acme-technical]]: 30 ms skew question; improvement noted in [[notes-acme-technical-interview]].
- Failure modes in [[chat-gemini-acme-system-design-prep]].

Pairs with [[skill-system-design]].
