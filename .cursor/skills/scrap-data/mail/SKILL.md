---
name: scrap-data-mail
description: Parse a local .mbox/.eml Gmail export into raw/inbox/mail-.../ with attachments. Use for scrap mail, download email thread. Do NOT fetch attachment bytes via an agent's Gmail MCP tools — there is no attachment-download tool and RAW MIME is too large for context.
---

# scrap-data / mail

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `scrap mail`, `download email thread`, `scrap-mail`

## Do NOT

- Fetch attachment bytes through Gmail MCP `get_thread`/`get_message` — there is no
  attachment-download tool, and `messageFormat: RAW` returns full base64 MIME that can
  be multi-MB per message and will blow an agent's context. Attachments must come from
  a local `.mbox`/`.eml` export (e.g. Google Takeout).
- Catalog or digest from here — `ingest-to-catalog/mail` and the digest skills do that

## CLI

```bash
python3 -m meta.ingest scrap-mail <path-to.mbox-or-.eml> [--slug thread-slug] [--force]
```

## Behavior

1. Dedup-checks the export file's bytes against `meta/corpus.tsv` (skip unless `--force`)
2. Parses every message via Python's stdlib `email`/`mailbox` — no third-party dependency
3. Sorts messages chronologically, renders `thread.md` (frontmatter: `thread-id`,
   `subject`, `participants`, `date-range`, `message-count`, then one `## <n>. <sender> —
   <date>` section per message)
4. Writes attachments flat inside the same folder as `<message-index>-<sanitized-name>`
5. Lands the bundle at `raw/inbox/mail-<YYYY-MM-DD>-<slug>/`

Subject-derived slugs that are empty after ASCII-kebab (e.g. Hebrew-only subjects) fall
back to `thread`; pass `--slug` to name the folder explicitly.

## Finding threads first

An agent can still use Gmail MCP `search_threads`/`get_thread` (PLAIN_TEXT) to find and
read a thread before you export it — that's fine, it's the export-to-disk step (for
attachment fidelity) that must happen outside the agent context. Tell the user which
query/thread to export from Google Takeout or their mail client.
