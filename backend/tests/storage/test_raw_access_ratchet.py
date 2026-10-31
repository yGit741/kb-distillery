"""No new module may reach raw/ directly, and the list of old ones only shrinks (see kb.lint.raw_access)."""
import os
import unittest

from kb.lint import raw_access

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_access_baseline.txt")


def baseline():
    with open(BASELINE, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip() and not l.startswith("#")}


class RawAccessRatchet(unittest.TestCase):
    def test_a_new_module_must_use_a_storage_connector(self):
        new = sorted(set(raw_access.scan()) - baseline())
        self.assertEqual(new, [], "these modules reach raw/ directly: use kb.storage.for_kb() instead "
                                  "(see meta-defaults/docs/storage.md), or add them to raw_access_baseline.txt "
                                  "only with a reason in the PR")

    def test_a_cleaned_up_module_leaves_the_baseline(self):
        stale = sorted(baseline() - set(raw_access.scan()))
        self.assertEqual(stale, [], "these modules no longer reach raw/ directly: delete them from "
                                    "backend/tests/storage/raw_access_baseline.txt so the list keeps shrinking")

    def test_the_connectors_and_migrations_are_exempt(self):
        found = raw_access.scan()
        self.assertFalse([m for m in found if m.startswith(("storage/", "migrations/"))])


if __name__ == "__main__":
    unittest.main()
