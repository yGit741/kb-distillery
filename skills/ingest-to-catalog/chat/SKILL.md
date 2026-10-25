---
name: ingest-to-catalog-chat
description: Catalog a Gemini-style chat export .md from inbox to raw/llm-chats/, rewriting an existing digest's raw field if one already cites it. Zero LLM. Do NOT digest from here.
---

# ingest-to-catalog / chat

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on an inbox `.md` whose content matches the `**You**` / `**Gemini**` turn-marker
  pattern (content-sniffed by `detect`, not filename-based)

## Do NOT

- Digest — use easy/full/deep digest skills after catalog (a digested chat is an `ai-chat` `chat-` page)
- Re-title a page that already digests this raw file — only the `raw:` field is rewritten
- Create a wiki stub — chats stay corpus rows until something is digested from them

## Behavior

1. Move `raw/inbox/<name>.md` → `raw/llm-chats/<ascii-slug>.md`
2. Optional `--collection` → corpus `collection` (+ a Contents row on a course/series collection)
3. If an existing `wiki/*.md` page's `raw:` equals the old inbox path (a prior hand-digest),
   rewrite that `raw:` line in place to the new path; `status`/content untouched
4. Lint runs at the end

This is how `raw/inbox/` drains for chat exports already cited by a digest.

## CLI

```bash
python3 -m kb.ingest catalog raw/inbox/<chat-export>.md [--collection <collection>]
```
