"""Bite test: prove the harness fails when the pipeline is broken. (~4 min; not part of `pixi run test`.)

    pixi run harness-bite

Each mutation edits the tool code inside the SCRATCH vault only (never this checkout) and the harness
must then exit non-zero:

  field-rename     draft.py writes the retired `digestion-status:` instead of `depth:` -> a hard gate (finalize's
                   `lint --ingest-strict` / lint) must trip, i.e. the run FAILS at a step;
  silent-text      draft.py renames one section heading -> nothing errors, only the goldens notice,
                   i.e. the run FAILS with a unified diff.
"""
import sys
from pathlib import Path

from . import run_pipeline


def _edit(rel, old, new):
    def mutate(root):
        p = Path(root) / rel
        text = p.read_text(encoding="utf-8")
        if old not in text:
            raise RuntimeError(f"bite mutation target not found in {rel}: {old!r}")
        p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return mutate


MUTATIONS = {
    "field-rename": (_edit("backend/src/kb/ingest/draft.py", "depth: {digestion}", "digestion-status: {digestion}"), "step-failure"),
    "silent-text": (_edit("backend/src/kb/ingest/draft.py", "## Proof idea (sketch only)", "## Proof sketch"), "golden-diff"),
}


def main():
    ok = True
    for name, (mutate, expect) in MUTATIONS.items():
        code, h = run_pipeline.run(mutate=mutate, quiet=True)
        diffs, _ = h.compare(update=False) if not h.failures else ([], 0)
        failed_steps = [f.split(":")[0] for f in h.failures]
        bit = code != 0 and ((expect == "step-failure" and failed_steps) or (expect == "golden-diff" and diffs and not failed_steps))
        print(f"mutation {name}: harness exit {code}; failed steps {failed_steps or 'none'}; "
              f"golden artifacts differing {len(diffs)} -> {'BITES' if bit else 'DID NOT BITE'}")
        if diffs:
            print("  first diff lines: " + " | ".join(diffs[0].splitlines()[:6]))
        if h.failures:
            print("  first failure: " + h.failures[0].splitlines()[0][:200])
        ok &= bool(bit)
    print("BITE TEST PASSED: the harness fails when the pipeline is broken" if ok else "BITE TEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
