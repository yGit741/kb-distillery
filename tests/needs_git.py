"""Marker for tests that need the engine checkout to be a git repository (history, the index, `ship`).

A `git archive` tarball is a valid source tree without a `.git`: the suite must collect and pass there, so these tests
skip with a reason instead of failing."""
import pytest

from kb_distillery.config import resources

needs_git = pytest.mark.skipif(not resources.has_git(),
                               reason="needs a git clone of kb-distillery; this source tree has no .git (a git archive?)")
