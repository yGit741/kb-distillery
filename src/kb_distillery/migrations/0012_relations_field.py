"""Relations field (schema 1.4): pages may carry a `relations:` block of typed links to other pages.

    relations:
      - to: other-page-slug
        kind: extends            # one of the kb.toml `[edges] types`
        note: why it holds       # required for the kinds in `[edges] note_required` (contradicts)

Nothing on disk changes: relations are added page by page after review (one kb(refine) step per batch), and lint
checks the ones that are there. This migration exists so the schema bump is recorded in meta/migrations/applied.tsv
like every other one. Idempotent.

    python src/kb_distillery/migrations/0012_relations_field.py [--root R] [--dry-run]
"""
import argparse

PRODUCES = (1, 4)


def apply(root, dry_run=False):
    """No page is rewritten → [] (the list of changed files)."""
    return []


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(f"changed {len(apply(a.root, a.dry_run))} file(s)")
