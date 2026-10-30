# Acme technical interview — notes

Date: 2026-10-15, 11:00, video call. Interviewer: Omer Shahar (staff ML engineer, perception).

## Questions
1. Walk through a model you trained and shipped; what broke in production?
2. Implement a minimal multi-object tracker (assignment between detections and tracks). Discussed Hungarian matching vs greedy.
3. How would you fuse lidar and camera detections when timestamps differ by 30 ms?
4. PyTorch: why does a DataLoader with many workers sometimes slow training down?
5. Short design sketch: retraining trigger for a detector after a new warehouse site is onboarded.

## What went well
- The tracker discussion; Omer liked that I raised track birth and death thresholds unprompted.
- The ML-ops answer built on my chat prep: shadow deployment and a golden set.

## What to improve
- I was slow on the timestamp-alignment question; should have proposed interpolation of the IMU first.
- Needed a hint on Hungarian algorithm complexity.

## Next
Omer said he would recommend moving on to the system-design round. Recruiter Noa Peretz will confirm the date.
