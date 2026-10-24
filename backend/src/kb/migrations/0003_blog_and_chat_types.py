"""Blog posts and AI chats become typed pages (schema 0.9).

New note types `blog-post` (prefix `blog-`) and `ai-chat` (prefix `chat-`): the type requires
the prefix and the prefix requires the type; both need `raw:`, and an ai-chat needs an
informative title plus a conversation tree in meta/chats/. Wikilinks inside code are ignored.

No existing note used either prefix or type, so nothing is rewritten: apply() only checks that
this still holds (idempotent). The blog-post pages themselves arrive as knowledge steps.
"""
import os

PRODUCES = (0, 9)
PREFIX = {"blog-post": "blog-", "ai-chat": "chat-"}


def apply(root):
    wiki = os.path.join(root, "wiki")
    clashes = []
    for name in os.listdir(wiki):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(wiki, name), encoding="utf-8") as f:
            head = f.read(600)
        typ = next((l.split(":", 1)[1].strip() for l in head.splitlines() if l.startswith("type:")), "")
        for t, prefix in PREFIX.items():
            if name.startswith(prefix) != (typ == t):
                clashes.append(name)
    if clashes:
        raise RuntimeError(f"notes break the blog/chat prefix rule — fix before migrating: {clashes[:5]}")
