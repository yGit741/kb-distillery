"""The share build (Cloudflare site) still assumes one repository holding code and content: it checks out a
*viewer* ref that must contain src/kb_distillery/share and reads `.github/workflows/deploy-main.yml`, `share/`
and `scripts/` from the vault. The knowledge-base split leaves Cloudflare untouched for now, so these tests
are skipped whenever the vault is not the explorer checkout. Run them from a monorepo-layout checkout
(`KB_ROOT=<explorer>`), or remove this file once the share build takes its viewer from CHECKOUT_ROOT."""
import os

import pytest

from kb_distillery.paths import CHECKOUT_ROOT, ROOT

SPLIT = os.path.realpath(ROOT) != os.path.realpath(CHECKOUT_ROOT)


def pytest_collection_modifyitems(items):
    if not SPLIT:
        return
    here = os.path.dirname(__file__)
    mark = pytest.mark.skip(reason="share build assumes the monorepo layout (code + content in one repo); Cloudflare untouched in the kb split")
    for item in items:
        if str(item.fspath).startswith(here):
            item.add_marker(mark)
