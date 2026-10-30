# Gemini chat: preparing for Acme system-design and ML-ops questions

Exported 2026-10-12. Model: Gemini.

**Dana:** I have a system-design round at a warehouse-robotics company next week. Perception ML role. What kind of design question should I expect?

**Gemini:** Likely candidates: design a pipeline that detects and tracks objects for a fleet of robots, or design the retraining loop for a perception model. Structure your answer: requirements and constraints (latency, edge compute, safety), data flow, model choice, evaluation, deployment, monitoring.

**Dana:** Give me the ML-ops angle.

**Gemini:** Cover these: dataset versioning, a golden evaluation set per scenario, CI that blocks a model if recall on pedestrians drops, shadow deployment before rollout, drift monitors on input statistics, and a rollback path. Mention retraining triggers: a drift alert, a new site, or a failure cluster found in the field.

**Dana:** How do I talk about sensor fusion in a design round?

**Gemini:** Draw the stack: raw lidar, camera, IMU; time synchronisation; a per-sensor detector; a fusion stage such as a Kalman filter or learned late fusion; a tracker. Name the failure modes: timestamp skew, calibration drift, one sensor going blind.

**Dana:** Any trick for the latency budget?

**Gemini:** State the budget first (for example 50 ms end to end on the robot), allocate it per stage, then say what you would quantize or prune first and how you would measure the accuracy loss.

**Dana:** Summarise a checklist.

**Gemini:** 1. Clarify requirements. 2. Sketch data flow. 3. Pick models and justify. 4. Evaluation plan with a golden set. 5. Deployment: shadow, canary, rollback. 6. Monitoring and retraining triggers. 7. Trade-offs you would revisit with more time.
