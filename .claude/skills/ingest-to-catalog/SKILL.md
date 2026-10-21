---
name: ingest-to-catalog
description: Move inbox files to typed raw/ folders and create lean wiki stubs. Zero LLM. Use for "catalog", "triage inbox", "ingest to catalog". Do NOT read PDFs or digest.
---

# ingest-to-catalog

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog`, `triage inbox`, `ingest to catalog`, `drain inbox`

## Do NOT

- Read PDF body text
- Run any digest tier
- Write wiki prose beyond the stub template

## CLI

```bash
python3 -m meta.ingest catalog <inbox-path> [--course misc]
python3 -m meta.ingest drain-inbox [--course misc]
```

## Subskills

| Subskill | Role |
|----------|------|
| [detect](detect/SKILL.md) | Inspect file → route handler |
| [articles](articles/SKILL.md) | PDF → `raw/papers/<course>/` + wiki stub |
| [mail](mail/SKILL.md) | thread bundle → `raw/mail/<dir>/` + `type: source` stub |
| [chat](chat/SKILL.md) | Gemini-style `.md` export → `raw/chats/` + `type: source` stub |
| [notes](notes/SKILL.md) | notes handler (stub) |
| [slides](slides/SKILL.md) | slides handler (stub) |
| [web](web/SKILL.md) | web handler (stub) |
| [blog](blog/SKILL.md) | blog handler (stub) |

## Output

Wiki stub with `digestion-status: catalog`, `status: to-read` (`mail`/`chat` create
`type: source` stubs instead — no `digestion-status`). Run `pixi run lint` after.
