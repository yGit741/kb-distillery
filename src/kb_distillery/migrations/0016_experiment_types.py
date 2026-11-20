"""Experiment types (schema 1.6): the research kit can hold empirical work.

New in the kit, nothing renamed:
  * source type `run` (`run-<name>`): one experiment run, a frozen bundle under raw/experiments/<run>/
    (run.md is the raw item; config, summary and history files beside it are its assets);
  * collection type `experiment` (`exp-<name>`): the design, with a Contents table of its runs;
  * concept types `conjecture` (`conj-`; sketch, partial, proved, refuted), `result` (`result-`; supports,
    refutes, inconclusive) and `method` (`method-`);
  * edge types `tests`, `supports`, `refutes`.

No page is rewritten: the types are additions and a kb gets them from its kit. This migration exists so the
schema bump is recorded in meta/migrations/applied.tsv like every other one. Idempotent.

    python src/kb_distillery/migrations/0016_experiment_types.py [--root R] [--dry-run]
"""
import argparse

PRODUCES = (1, 6)


def apply(root, dry_run=False):
    """No page is rewritten → [] (the list of changed files)."""
    return []


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(f"changed {len(apply(a.root, a.dry_run))} file(s)")
