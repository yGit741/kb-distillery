---
name: ingest-to-catalog-detect
description: Detect inbox file type and route to ingest-to-catalog handler. Zero LLM. Do NOT digest from here.
---

# ingest-to-catalog / detect

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- Runs inside `catalog` and `drain-inbox`

## Do NOT

- Digest — detection only routes to catalog handlers

## Routing rules

| Signal | Handler |
|--------|---------|
| `.pdf` + paper-like name (`YYYY-kebab.pdf`) | articles |
| `.pdf` (other) | articles (rename on catalog) |
| directory named `mail-*` | mail |
| `.ppt`, `.pptx`, `.key` | slides (stub) |
| `.md` matching You/Gemini turn markers (content-sniffed) | chat |
| `.md`, `.html`, `.htm` (other) | web (stub) |
| images (`.png`, `.jpg`, …) | notes (stub) |
| default | articles if PDF else notes |

## CLI

Detection runs inside:

```bash
python3 -m meta.ingest catalog raw/inbox/<file>
python3 -m meta.ingest drain-inbox
```

Prints detected type before routing.
