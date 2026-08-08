---
name: ingest-to-catalog-detect
description: Detect inbox file type and route to the correct ingest-to-catalog handler. Zero LLM. Used by catalog and drain-inbox commands.
---

# ingest-to-catalog / detect

**LLM tier:** none · **Budget:** 0 tokens

## Routing rules

| Signal | Handler |
|--------|---------|
| `.pdf` + paper-like name (`YYYY-kebab.pdf`) | articles |
| `.pdf` (other) | articles (rename on catalog) |
| `.ppt`, `.pptx`, `.key` | slides (stub) |
| `.md`, `.html`, `.htm` | web (stub) |
| images (`.png`, `.jpg`, …) | notes (stub) |
| default | articles if PDF else notes |

## CLI

Detection runs inside:

```bash
python3 -m meta.ingest catalog raw/inbox/<file>
python3 -m meta.ingest drain-inbox
```

Prints detected type before routing.
