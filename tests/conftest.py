"""Suite-wide isolation: tests never mint a real GitHub App token (kb_distillery.git.app_token).

The vault the suite reads is `tests/fixtures/kb/kb-fixture` (the explorer's default page types, a handful of
lint-valid pages) unless the caller picked a knowledge base with `KB` / `KB_ROOT`. The fixture is copied to a
session temp folder first, so tests that run lint or write pages never dirty the checked-in files.

Two groups of tests are tied to the vault they run against, and skip instead of failing on any other:
  * TYPE_BOUND modules build pages of the explorer's default types (paper, book, person, ...) and read the
    type tables `kb_distillery.core.schema` built at import time from the active kb.toml, so they run only when that
    kb declares the default types (the fixture and the thesis kb do; examples/demo does not);
  * THESIS_DATA modules read content only the thesis kb has (its raw chats, migration state, ops config):
    they run only with KB=yonatan-thesis.
`real_kb()` is for tests that read a real knowledge base (KB=<id>) rather than the fixture."""
import atexit
import os
import shutil
import tempfile

os.environ["KB_APP_CONFIG"] = os.path.join(os.sep, "nonexistent", "kb-app.toml")
# Sharing is a plugin that is off by default; the suite runs as the owner's machine does, with the Cloudflare publisher
# selected (every fake-backed share test relies on it). Tests of "no publisher" clear it themselves.
os.environ["KB_PUBLISHER"] = "cloudflare"
os.environ["KB_ENGINE_CONFIG"] = os.path.join(os.sep, "nonexistent", "kb-engine.toml")
FIXTURE_KB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kb", "kb-fixture")
if not os.environ.get("KB") and not os.environ.get("KB_ROOT"):
    _tmp = os.path.realpath(tempfile.mkdtemp(prefix="kb-fixture-"))   # realpath: /var -> /private/var on macOS
    os.environ["KB_ROOT"] = os.path.join(_tmp, "kb-fixture")
    shutil.copytree(FIXTURE_KB, os.environ["KB_ROOT"])
    atexit.register(shutil.rmtree, _tmp, True)
    # no kb picked = the fixture: the bases dir is an empty temp folder too, so nothing in a run can discover, lint or
    # write a real knowledge base under ~/knowledge (tests that need a bases dir build their own)
    os.environ["KB_DISTILLERY_HOME"] = os.path.join(_tmp, "bases")
    os.environ.pop("KB_BASES_DIR", None)
    os.makedirs(os.environ["KB_DISTILLERY_HOME"])

import pytest

TYPE_BOUND = {
    "core/test_model.py", "core/test_books.py", "core/test_persons.py", "core/test_source_model.py",
    "core/test_coherence.py", "core/test_scopes.py", "core/test_wikiio.py", "api/test_scopes.py",
    "search/test_scoped_query.py", "ingest/test_blog.py", "ingest/test_digest_robustness.py",
    "ingest/test_ingest_fixes.py", "ingest/test_youtube.py", "lint/test_links.py", "lint/test_lint_ci.py",
    "lint/test_question_pages.py", "lint/test_summary_lint.py", "ops/test_ops.py",
}
THESIS_DATA = {
    "ingest/test_chat_merge.py", "ops/test_notify.py", "metrics/test_metrics.py",
    "migrations/test_migrations.py", "services/test_lifecycle_data.py",
    # read the thesis kb's frozen migration artifacts and its kb-x.y.z tags
    "core/test_source_model.py::SpecMapTotality", "core/test_source_model.py::MigrationTests",
    "core/test_source_model.py::MajorVersionBump::test_share_build_reads_the_schema_major",
}


def real_kb() -> bool:
    """True when the suite runs against a real knowledge base (`KB=<id>`), not the fixture."""
    return bool(os.environ.get("KB")) and not os.environ.get("KB_ROOT")


def _has_default_types() -> bool:
    from kb_distillery.core import kbtypes
    return kbtypes.load().spec == kbtypes.build(None).spec


def pytest_collection_modifyitems(config, items):
    from kb_distillery import kbconfig
    cfg = kbconfig.current()
    thesis = bool(cfg) and cfg.id == "yonatan-thesis"
    default_types = _has_default_types()
    here = os.path.dirname(os.path.abspath(__file__))
    for item in items:
        rel = os.path.relpath(str(item.fspath), here).replace(os.sep, "/")
        node = rel + item.nodeid[item.nodeid.index("::"):] if "::" in item.nodeid else rel
        if rel in TYPE_BOUND and not default_types:
            item.add_marker(pytest.mark.skip(reason="needs the explorer's default page types (run with KB=yonatan-thesis or no KB)"))
        elif not thesis and any(node == t or node.startswith(t + "::") for t in THESIS_DATA):
            item.add_marker(pytest.mark.skip(reason="reads the thesis knowledge base's own content (run with KB=yonatan-thesis)"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", 'flag(name, on): run this test with feature flag `name` forced on/off '
        '(kb_distillery.flags.override); `python -m kb_distillery.flags.coverage` needs both states per flag')


@pytest.fixture(autouse=True)
def _flag_marker(request):
    from contextlib import ExitStack

    from kb_distillery.flags.registry import override
    with ExitStack() as stack:
        for m in request.node.iter_markers("flag"):
            stack.enter_context(override(m.args[0], m.args[1]))
        yield


@pytest.fixture(autouse=True)
def _no_real_claude_sessions(monkeypatch, tmp_path_factory):
    """`metrics.sessions.scan()` defaults to the owner's `~/.claude/projects` (hundreds of real session logs, ~5s to parse
    and a different answer on every machine): a sync that runs the nightly metrics step must see an empty one.
    Tests of the scanner pass their own `sources`."""
    from kb_distillery.metrics import sessions
    if "empty" not in _EMPTY_PROJECTS:
        _EMPTY_PROJECTS["empty"] = str(tmp_path_factory.mktemp("claude-projects"))
    monkeypatch.setattr(sessions, "PROJECTS_DIR", _EMPTY_PROJECTS["empty"])
    from kb_distillery.metrics import golden
    monkeypatch.setattr(golden, "PROJECTS_DIR", _EMPTY_PROJECTS["empty"])   # golden imported the value by name


_EMPTY_PROJECTS = {}
