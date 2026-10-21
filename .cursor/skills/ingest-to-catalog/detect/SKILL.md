---
name: ingest-to-catalog-detect
description: Detect an inbox file's format folder and route to the ingest-to-catalog handler. Zero LLM. Do NOT digest from here.
---

# ingest-to-catalog / detect

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- Runs inside `catalog` and `drain-inbox`

## Do NOT

- Digest — detection only routes to catalog handlers

## Routing rules

`raw/` is split by format (how the bytes were produced). Typed → `printed-docs`, by hand →
`handwritten`, slides → `presentations` whatever the extension.

| Signal | Format folder | Handler |
|--------|---------------|---------|
| `.pdf` with a text layer (≥200 chars/page over the first pages) | `printed-docs` | articles |
| `.pdf` without a text layer (reMarkable ink, scan) | `handwritten` | notes |
| directory named `mail-*` | `emails` | mail |
| `.ppt`, `.pptx`, `.key` | `presentations` | slides |
| `.md` matching You/Gemini turn markers (content-sniffed) | `llm-chats` | chat |
| `.md`, `.html`, `.htm` (other) | `web-clips` | web / blog |
| images (`.png`, `.jpg`, …) | `images` | — |
| anything else | error — pass `--format` | |

A slide deck exported as PDF has a text layer and lands in `printed-docs` — pass
`--format presentations`.

## CLI

```bash
python3 -m meta.ingest catalog raw/inbox/<file> [--format <folder>]
python3 -m meta.ingest drain-inbox
```

Prints `format → <folder>` before routing.
