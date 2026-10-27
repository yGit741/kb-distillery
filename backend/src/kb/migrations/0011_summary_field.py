"""Summary field (schema 1.3): pages may carry `summary:`, `summary_from:` and `summary_by:`.

Nothing on disk changes: the field is added page by page by `pixi run summarize -- apply` (one
kb(refine) step per batch), and lint only warns while pages lack it. This migration exists so the
schema bump is recorded in meta/migrations/applied.tsv like every other one. Idempotent.

    python backend/src/kb/migrations/0011_summary_field.py [--root R] [--dry-run]
"""
import argparse

PRODUCES = (1, 3)


def apply(root, dry_run=False):
    """No page is rewritten → [] (the list of changed files)."""
    return []


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(f"changed {len(apply(a.root, a.dry_run))} file(s)")
