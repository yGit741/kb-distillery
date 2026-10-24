"""raw/ by format × corpus.tsv `collection` × type-prefixed slugs (schema 0.10).

raw/papers|notes|slides|mail|chats|web|assets → printed-docs|handwritten|presentations|emails|
llm-chats|web-clips|images (flat, `<short>-<topic>` names; a notes PDF with no text layer is
handwritten). Course MOC + source pages merge into course-/series- hubs with a ## Contents table;
moc-<theme> → theme-<theme>; papers/books/parts get paper-/book-/part- prefixes; a chat with a
meta/chats/ tree becomes an ai-chat page, the rest of the substantive chats and email threads
conversation pages; stub chat/mail pages go to _quarantine/. Every renamed page keeps its old slug in
`aliases:`; digestion-status is backfilled on every reading unit.

The PR carries the rewritten notes and the moves of git-tracked raw files. Gitignored raw files
(PDFs) and corpus.tsv cannot ride in it, so apply() also writes meta/migration/0004-finish.json;
after the merge run `python3 -m kb.maintenance.migrate_model --finish` in the primary checkout.

Needs meta/migration/collections.tsv filled in (refuses while TODO cells remain). Idempotent: on an
already-migrated vault the plan is empty and nothing is written.
"""
import os
import sys

PRODUCES = (0, 10)


def apply(root):
    meta = os.path.join(root, "meta")
    from kb.maintenance import migrate_model
    migrate_model.run_for_migration(root)
