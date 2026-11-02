---
type: skill
layer: concept
title: "ML-ops"
maturity: growing
sources: [{resource: chat-gemini-acme-system-design-prep.md}, {resource: posting-acme-senior-ml-engineer.md}, {resource: notes-acme-technical-interview.md}]
related: [role-senior-ml-engineer-acme.md, skill-system-design.md, interview-acme-technical.md, company-acme-robotics.md]
description: "ML-ops skills Acme expects: dataset versioning, golden evaluation sets, CI for models, shadow deployment, drift monitoring and retraining triggers."
generated: {by: human:dana-levi}
---

# ML-ops

Practical operation of models in production.

## Checklist
Golden set per scenario, a CI gate on pedestrian recall, shadow deployment, drift monitors, rollback, retraining triggers (drift alert, new site, failure cluster). Source: [[chat-gemini-acme-system-design-prep]].

## Where it was tested
A retraining-trigger question in [[interview-acme-technical]]. Required by [[role-senior-ml-engineer-acme]]; pairs with [[skill-system-design]].
