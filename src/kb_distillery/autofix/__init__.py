"""Nightly failure auto-fix: a red nightly run opens (or reuses) one `nightly-fail` issue per failure signature,
and an engine failure goes to a fixer whose PR merges itself unless the diff gate calls it dramatic.

    detect.py   read the last run of meta/.ops/runs.jsonl, turn it into failures with a stable signature
    issue.py    open or reuse the GitHub issue for a signature (never fails the nightly)
    gate.py     measure a diff: the reasons a fix must wait for the owner (empty = may merge itself)
    __main__    `python -m kb_distillery.autofix nightly|gate`

Flag `nightly-autofix` (runtime): the nightly (`ops.core.sync_hygiene`) starts `nightly` only when it is on.
"""
FLAG = "nightly-autofix"
LABEL = "nightly-fail"
