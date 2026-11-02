"""Search cards: one tiny markdown file per page — its title and `description:` line — for the qmd service.

    python -m kb_distillery.search.cards        (lint runs it after every check; cheap: only changed cards are written)

Cards live in `.cache/qmd-cards/<slug>.md` (never committed). A page gets a card only when it has a
summary; courses and `listed` stubs never do (kb_distillery.vault.summary.needs_summary). A card whose page lost its
summary or was deleted is removed. Unchanged cards keep their mtime, so qmd re-embeds only what changed.
"""
import os
import sys

from kb_distillery.config import paths
from kb_distillery.vault import frontmatter
from kb_distillery.vault.summary import needs_summary, unquote
from kb_distillery.vault.schema import is_page_file

CARDS_DIR = os.path.join(paths.CACHE_PATH, "qmd-cards")


def card_text(slug, fm, text):
    """'# <title>\\n\\n<summary>\\n' or None when the page gets no card."""
    summary = unquote(fm.get("description"))
    if not summary or not needs_summary(fm):
        return None
    title = frontmatter.page_title(fm, text, slug)
    return f"# {title}\n\n{summary}\n"


def build(wiki_dir=None, cards_dir=None):
    """Sync the cards folder with wiki/ → {'written': n, 'removed': n, 'cards': n}."""
    from kb_distillery.lint.lint import parse_frontmatter      # lazy: lint imports this module
    wiki_dir = wiki_dir or paths.WIKI_PATH
    cards_dir = cards_dir or CARDS_DIR
    os.makedirs(cards_dir, exist_ok=True)
    want = {}
    for name in os.listdir(wiki_dir):
        if not is_page_file(name):
            continue
        with open(os.path.join(wiki_dir, name), encoding="utf-8") as f:
            text = f.read()
        card = card_text(name[:-3], parse_frontmatter(text) or {}, text)
        if card:
            want[name] = card
    written = removed = 0
    for name, card in want.items():
        p = os.path.join(cards_dir, name)
        try:
            with open(p, encoding="utf-8") as f:
                if f.read() == card:
                    continue
        except FileNotFoundError:
            pass
        with open(p, "w", encoding="utf-8") as f:
            f.write(card)
        written += 1
    for name in os.listdir(cards_dir):
        if name.endswith(".md") and name not in want:
            os.remove(os.path.join(cards_dir, name))
            removed += 1
    return {"written": written, "removed": removed, "cards": len(want)}


if __name__ == "__main__":
    r = build()
    print(f"cards: {r['cards']} ({r['written']} written, {r['removed']} removed) → {CARDS_DIR}")
    sys.exit(0)
