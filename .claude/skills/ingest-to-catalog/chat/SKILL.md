---
name: ingest-to-catalog-chat
description: Catalog a Gemini-style chat export .md from inbox to raw/chats/, rewriting an existing digest's raw field if one already cites it. Zero LLM. Do NOT digest from here.
---

# ingest-to-catalog / chat

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on an inbox `.md` whose content matches the `**You**` / `**Gemini**` turn-marker
  pattern (content-sniffed by `detect`, not filename-based)

## Do NOT

- Digest — use easy/full/deep digest skills after catalog
- Re-title a page that already digests this raw file — only the `raw:` field is rewritten

## Behavior

1. Move `raw/inbox/<name>.md` → `raw/chats/<ascii-slug>.md`
2. Look for an existing `wiki/*.md` page whose `raw:` already equals the old inbox path
   (a prior hand-digest, e.g. `wiki/source-gemini-*.md`)
   - **found** → rewrite that page's `raw:` line in place to the new `raw/chats/` path;
     `status`/content untouched
   - **not found** → create a lean `wiki/source-chat-<slug>.md` stub: `type: source`,
     `format: chat`, `status: to-read`
3. Run lint (via caller)

This is the only way `raw/inbox/` fully drains for chat exports — before this handler
existed, digested Gemini chats stayed stranded in inbox because nothing moved them out
from under an already-cited `raw:` path.

## CLI

```bash
python3 -m meta.ingest catalog raw/inbox/<chat-export>.md
```
