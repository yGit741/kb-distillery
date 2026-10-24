"""The layout rules of the `meta/` -> `backend/` move, as data.

Everything the restructure does is derived from these tables, so a re-run after `main` gained new
files routes them by the same rules; a file no rule claims is *reported*, never guessed.
"""
import fnmatch

PKG = "backend/src/kb"          # the importable package `kb`
TESTS = "backend/tests"

# --- top-level modules meta/<name>.py -> package -------------------------------------------------
TOP_MODULES = {
    # core: the schema and what is built straight on it
    "schema": "core", "graph": "core", "hubs": "core", "scopes": "core", "persons": "core",
    "books": "core", "wikiio": "core", "mathnorm": "core", "coherence": "core", "health": "core",
    # lint
    "lint": "lint", "lint_skills": "lint",
    # search
    "query": "search", "semfind": "search", "explore_raw": "search", "citations": "search",
    # git lifecycle
    "guard": "git", "git_guard": "git", "commit_policy": "git", "ship": "git",
    "merge_nudge": "git", "curate_history": "git",
    # maintenance
    "daily_sync": "maintenance", "notify": "maintenance", "sync_skills": "maintenance",
    "rename_raw": "maintenance", "migrate_model": "maintenance", "export": "maintenance",
    "fix_math": "maintenance",
}

# --- subpackages moved whole (same name) ----------------------------------------------------------
WHOLE_PACKAGES = ["ingest", "distill", "ops", "report", "share"]

# meta/share/<x> that is NOT part of the python package: -> top-level `share/` (the Cloudflare Worker)
SHARE_WORKER_FROM = "meta/share/worker"
SHARE_WORKER_TO = "share"

# --- meta/dashboard/* ----------------------------------------------------------------------------
# former *_data.py modules -> kb.services (pure functions, no HTTP); named without retired words.
DASHBOARD_TO_SERVICES = {
    "graph_data": "graph",
    "explore_data": "pages",
    "corpus_data": "corpus",
    "scopes_data": "scopes",
    "chat_data": "chat",
    "schema_data": "schema",
    "chat_agent": "chat_agent",
    "digestion_data": "pipeline",
    "lifecycle_data": "lifecycle",
    "ops_data": "ops",
    "raw_layer": "raw_layer",
}
# the legacy server + pages stay together until their screens are ported (Phase 4)
DASHBOARD_STAYS = ["__init__.py", "__main__.py", "serve.py", "shell.py", "render.py", "ops_routes.py"]
DASHBOARD_PROMPTS_TO = f"{PKG}/prompts"          # meta/dashboard/prompts/*.md

# --- tools / skills -------------------------------------------------------------------------------
DIR_MOVES = [
    ("meta/skills", "skills"),
    ("meta/githooks", "tools/githooks"),
    ("meta/launchd", "tools/launchd"),
]
FILE_MOVES = [
    ("meta/launch.sh", "tools/launch.sh"),
]

# --- vault metadata: stays in meta/ ----------------------------------------------------------------
META_FILES_STAY = {"meta/ops/sync.toml"}           # the owner's config (email, notify mode): vault-level, not code
META_STAYS = {
    "corpus.tsv", "log.md", "aliases.tsv", "coherence-warnings.tsv", "raw-renames.tsv", "thesis.md",
    "web-clipper.md", "automation-daily-sync.md", "model-spec.md", "chats", "templates", "migration",
}
# meta/migrations: code -> package, applied.tsv stays
MIGRATIONS_CODE_TO = f"{PKG}/migrations"
MIGRATIONS_DATA_STAYS = {"applied.tsv"}
# meta/<dot-dir> are runtime state (gitignored); never touched
RUNTIME_DOT_DIRS = True

# --- tests ------------------------------------------------------------------------------------------
# meta/test_<x>.py -> backend/tests/<package>/test_<x>.py. Unlisted -> backend/tests/ (and reported).
TEST_PACKAGE = {
    "adopt": "ops", "ops": "ops", "hygiene": "ops", "threads": "ops",
    "arxiv_integrity": "ingest", "blog": "ingest", "chat_kb": "ingest", "chat_merge": "ingest",
    "chat_store": "ingest", "chat": "ingest", "digest_robustness": "ingest", "easy_batch": "ingest",
    "ingest_fixes": "ingest", "researcher": "ingest", "resolve": "ingest", "wordpress": "ingest",
    "books": "core", "coherence": "core", "health": "core", "hubs": "core", "mathnorm": "core",
    "persons": "core", "scopes": "core", "model": "core",
    "citations": "search", "explore_raw": "search", "scoped_query": "search", "semfind": "search",
    "commit_policy": "git", "curate_history": "git", "git_guard": "git", "guard": "git",
    "merge_nudge": "git", "ship": "git",
    "daily_sync": "maintenance", "migrate_model": "maintenance", "notify": "maintenance",
    "links": "lint", "lint_ci": "lint", "pdf_integrity": "lint", "skills": "lint",
    "migrations": "migrations", "wikiio": "core", "invariants": "core", "source_model": "core",
    "spotcheck": "ingest", "graph_ui": "dashboard", "source_layer_ui": "dashboard", "pipeline_e2e": "ingest",
    "report": "report",
    "share_build": "share", "share_ci": "share", "share_deploy": "share", "share_scaffold": "share",
    "share_snapshots": "share", "share_tabs": "share",
    "chat_agent": "services", "corpus_data": "services", "digestion_data": "services",
    "graph_data": "services", "lifecycle_data": "services", "ops_data": "services",
    "pipeline_status": "services", "scopes_ui": "services",
    "serve_thumb": "dashboard", "start_page": "dashboard",
}

# --- dotted-module map (old import name -> new dotted name) ---------------------------------------
def module_map():
    """{old dotted/bare name: new dotted name} for every module the codemod must follow."""
    m = {}
    for name, pkg in TOP_MODULES.items():
        m[name] = f"kb.{pkg}.{name}"
    for pkg in WHOLE_PACKAGES:
        m[pkg] = f"kb.{pkg}"
    for old, new in DASHBOARD_TO_SERVICES.items():
        m[old] = f"kb.services.{new}"
        m[f"dashboard.{old}"] = f"kb.services.{new}"
    for stay in DASHBOARD_STAYS:
        mod = stay[:-3]
        if mod != "__init__":
            m[f"dashboard.{mod}"] = f"kb.dashboard.{mod}"
    for name, pkg in TEST_PACKAGE.items():       # test modules importing each other's helpers
        m[f"test_{name}"] = f"tests.{pkg}.test_{name}"
    m["dashboard"] = "kb.dashboard"
    return m


def package_of_new(path):
    """kb.<pkg> package (dotted) that a new module path lives in."""
    rel = path[len(PKG) + 1:]
    return "kb." + rel.split("/")[0] if "/" in rel else "kb"


def match_any(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)
