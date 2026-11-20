"""codekb: turn repositories (or a folder of code) into a deterministic IR and cut it into citable cards.

    kb_distillery.codekb.generic   project file, typed graph (JSON + SQLite), history, cards
    kb_distillery.codekb.cpp       C and C++ (tree-sitter, optional: pip install "kb-distillery[code]")
    kb_distillery.codekb.pylang    Python (the standard `ast` module)
    kb_distillery.codekb.cli       `distill code ...`

No model and no network: the same commits always give the same output. See docs/guides/code-kb.md.
"""
