"""codekb: turn git repositories (or a folder of code) into a deterministic IR, cut it into citable cards, and check what
wiki pages cite.

    kb_distillery.codekb.generic   project file, typed graph (JSON + SQLite), history, cards, staleness, the artifact graph
    kb_distillery.codekb.cpp       C and C++ (tree-sitter, optional: pip install "kb-distillery[code]")
    kb_distillery.codekb.pylang    Python (the standard `ast` module)
    kb_distillery.codekb.cites     {{card:Fid}} placeholders and fact citations in wiki pages (check only)
    kb_distillery.codekb.export    cards into a kb's raw/ as one `kb(catalog)` step
    kb_distillery.codekb.cli       `distill code ...`

No model and no network: the same commits always give the same output. See docs/guides/code-kb.md.
"""
