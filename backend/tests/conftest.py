"""Suite-wide isolation: tests never mint a real GitHub App token (kb.git.app_token)."""
import os

os.environ["KB_APP_CONFIG"] = os.path.join(os.sep, "nonexistent", "kb-app.toml")

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", 'flag(name, on): run this test with feature flag `name` forced on/off '
        '(kb.flags.override); `python -m kb.flags.coverage` needs both states per flag')


@pytest.fixture(autouse=True)
def _flag_marker(request):
    from contextlib import ExitStack

    from kb.flags.registry import override
    with ExitStack() as stack:
        for m in request.node.iter_markers("flag"):
            stack.enter_context(override(m.args[0], m.args[1]))
        yield
