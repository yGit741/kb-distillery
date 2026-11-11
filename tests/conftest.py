"""Suite-wide isolation: tests never mint a real GitHub App token (kb_distillery.git.app_token).

The vault the suite reads is `tests/fixtures/kb/kb-fixture` (the explorer's default page types, a handful of
lint-valid pages) unless the caller picked a knowledge base with `KB` / `KB_ROOT`. The fixture is copied to a
session temp folder first, so tests that run lint or write pages never dirty the checked-in files.

Two groups of tests are tied to the vault they run against, and skip instead of failing on any other:
  * TYPE_BOUND modules build pages of the explorer's default types (paper, book, person, ...) and read the
    type tables `kb_distillery.vault.schema` built at import time from the active kb.toml, so they run only when that
    kb declares the default types (the fixture and a research kb do; examples/demo does not);
  * THESIS_DATA modules read content only the maintainer's research kb has (its raw chats, migration state, ops config):
    they run only against the kb named by $KB_TEST_DATA_KB (the maintainer's research kb).
`real_kb()` is for tests that read a real knowledge base (KB=<id>) rather than the fixture."""
import atexit
import os
import shlex
import shutil
import sys
import tempfile

os.environ["KB_APP_CONFIG"] = os.path.join(os.sep, "nonexistent", "kb-app.toml")
# Sharing is a plugin that is off by default; the suite runs as the owner's machine does, with the Cloudflare publisher
# selected (every fake-backed share test relies on it). Tests of "no publisher" clear it themselves.
os.environ["KB_PUBLISHER"] = "cloudflare"
os.environ["KB_ENGINE_CONFIG"] = os.path.join(os.sep, "nonexistent", "kb-engine.toml")
# The share config is a fixture too: an invented account, so no test reads (or needs) the owner's ~/.config/kb-distillery/share.toml.
os.environ["KB_SHARE_CONFIG"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "share", "share.toml")
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

# `distill` on PATH, running THIS checkout: the git hooks a kb installs call it by name (`command -v distill`, fail closed),
# a clean machine (CI) has none, and a developer's own launcher would run some other checkout's code.
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
_shim_dir = tempfile.mkdtemp(prefix="kb-distill-shim-")
atexit.register(shutil.rmtree, _shim_dir, True)
with open(os.path.join(_shim_dir, "distill"), "w", encoding="utf-8") as _f:     # shlex: a `$`, quote or brace in a path stays literal
    _f.write(f'#!/bin/sh\n[ -n "$PYTHONPATH" ] || PYTHONPATH={shlex.quote(_SRC)}\nexport PYTHONPATH\n'
             f'exec {shlex.quote(sys.executable)} -m kb_distillery.cli "$@"\n')
os.chmod(os.path.join(_shim_dir, "distill"), 0o755)
os.environ["PATH"] = _shim_dir + os.pathsep + os.environ.get("PATH", "")

import pytest

TYPE_BOUND = {
    "vault/test_model.py", "vault/test_books.py", "vault/test_persons.py", "vault/test_source_model.py",
    "vault/test_coherence.py", "vault/test_scopes.py", "vault/test_wikiio.py", "server/test_scopes.py",
    "search/test_scoped_query.py", "ingest/sources/web/test_blog.py", "ingest/test_digest_robustness.py",
    "ingest/test_ingest_fixes.py", "ingest/sources/youtube/test_youtube.py", "lint/test_links.py", "lint/test_lint_ci.py",
    "lint/test_question_pages.py", "lint/test_summary_lint.py", "ops/test_ops.py",
}
THESIS_DATA = {
    "ingest/sources/chat/test_chat_merge.py", "ops/test_notify.py", "metrics/test_metrics.py",
    "migrations/test_migrations.py", "services/test_lifecycle_data.py",
    # read the thesis kb's frozen migration artifacts and its kb-x.y.z tags
    "vault/test_source_model.py::SpecMapTotality", "vault/test_source_model.py::MigrationTests",
    "vault/test_source_model.py::MajorVersionBump::test_share_build_reads_the_schema_major",
}


def real_kb() -> bool:
    """True when the suite runs against a real knowledge base (`KB=<id>`), not the fixture."""
    return bool(os.environ.get("KB")) and not os.environ.get("KB_ROOT")


def _has_default_types() -> bool:
    from kb_distillery.vault import kbtypes
    return kbtypes.load().spec == kbtypes.build(None).spec


def pytest_collection_modifyitems(config, items):
    from kb_distillery.config import kb as kbconfig
    cfg = kbconfig.current()
    thesis = bool(cfg) and bool(os.environ.get("KB_TEST_DATA_KB")) and cfg.id == os.environ["KB_TEST_DATA_KB"]
    default_types = _has_default_types()
    here = os.path.dirname(os.path.abspath(__file__))
    for item in items:
        rel = os.path.relpath(str(item.fspath), here).replace(os.sep, "/")
        node = rel + item.nodeid[item.nodeid.index("::"):] if "::" in item.nodeid else rel
        if rel in TYPE_BOUND and not default_types:
            item.add_marker(pytest.mark.skip(reason="needs the explorer's default page types (run with a research kb or no KB)"))
        elif not thesis and any(node == t or node.startswith(t + "::") for t in THESIS_DATA):
            item.add_marker(pytest.mark.skip(reason="reads the thesis knowledge base's own content (run with KB=<id> and KB_TEST_DATA_KB=<id>)"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", 'flag(name, on): run this test with feature flag `name` forced on/off '
        '(kb_distillery.config.flags.override); `python -m kb_distillery.config.flags.coverage` needs both states per flag')


@pytest.fixture(autouse=True)
def _flag_marker(request):
    from contextlib import ExitStack

    from kb_distillery.config.flags.registry import override
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


@pytest.fixture(autouse=True)
def _no_citation_fetch(monkeypatch):
    """Cataloging a paper fetches its citations from Semantic Scholar: tests never touch the network
    (`tests/ingest/test_catalog_citations.py` covers the hook with a fake)."""
    monkeypatch.setenv("KB_INGEST_CITATIONS", "0")
