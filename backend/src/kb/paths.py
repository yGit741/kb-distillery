"""Where the vault is, and where everything in it lives. The ONE resolver.

`vault_root()` is the vault (content) checkout: `$KB_ROOT` when set (the share build points it at an
archived content ref), else the checkout this code runs from. Every module reads paths from here instead
of recomputing them from `__file__`. Data paths are absolute constants built from the schema's
repo-relative names (`kb.core.schema`), so renaming a vault folder is one edit in the schema.

Layout (code vs vault): code lives in `backend/src/kb`; vault metadata (corpus.tsv, log.md, chats/,
templates/, migration state) stays in `meta/`.
"""
import os

# backend/src/kb/paths.py -> kb -> src -> backend -> <checkout root>
CODE_DIR = os.path.dirname(os.path.abspath(__file__))                       # .../backend/src/kb
CHECKOUT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CODE_DIR)))  # the checkout this code runs from


def vault_root():
    """The vault checkout: $KB_ROOT, else the checkout this code runs from."""
    return os.environ.get("KB_ROOT") or CHECKOUT_ROOT


ROOT = vault_root()
META_DIR = os.path.join(ROOT, "meta")      # vault metadata only (no code lives here any more)


def vpath(*parts, root=None):
    """A path inside the vault: vpath("wiki", "x.md")."""
    return os.path.join(root or ROOT, *parts)


def _rel(name, default):
    try:
        from kb.core import schema
        return getattr(schema, name, default)
    except Exception:       # schema not importable (bootstrap): fall back to the documented name
        return default


# --- vault content ---------------------------------------------------------------------------------
WIKI_PATH = vpath(_rel("WIKI_DIR", "wiki"))
RAW_PATH = vpath(_rel("RAW_DIR", "raw"))
THINK_PATH = vpath(_rel("THINK_DIR", "think"))
INDEX_PATH = vpath("index.md")
QUARANTINE_PATH = vpath(_rel("QUARANTINE_DIR", "_quarantine"))

# --- vault metadata (meta/) ---------------------------------------------------------------------------
MANIFEST_PATH = vpath(_rel("MANIFEST", "meta/corpus.tsv"))
LOG_PATH = vpath("meta", "log.md")
ALIASES_PATH = vpath("meta", "aliases.tsv")
COHERENCE_PATH = vpath("meta", "coherence-warnings.tsv")
RAW_RENAMES_PATH = vpath("meta", "raw-renames.tsv")
CHATS_PATH = vpath("meta", "chats")
TEMPLATES_PATH = vpath("meta", "templates")
MIGRATIONS_APPLIED_PATH = vpath("meta", "migrations", "applied.tsv")

# --- runtime state (gitignored) -------------------------------------------------------------------------
OPS_PATH = vpath(_rel("OPS_DIR", "meta/.ops"))
INGEST_PATH = vpath(_rel("INGEST_DIR", "meta/.ingest"))
DISTILL_PATH = vpath(_rel("DISTILL_DIR", "meta/.distill"))
CATALOG_PATH = vpath("meta", ".catalog")
SEMFIND_PATH = vpath("meta", ".semfind")
RESEARCHER_PATH = vpath("meta", ".researcher")
MIGRATE_PATH = vpath("meta", ".migrate")
CACHE_PATH = vpath(".cache")
EXPORT_PATH = vpath(".exported")

# --- code-side resources (relative to the checkout the code runs from) ------------------------------------
SKILLS_PATH = os.path.join(CHECKOUT_ROOT, "skills")
TOOLS_PATH = os.path.join(CHECKOUT_ROOT, "tools")
PROMPTS_PATH = os.path.join(CODE_DIR, "prompts")
MIGRATIONS_CODE_PATH = os.path.join(CODE_DIR, "migrations")
SHARE_WORKER_PATH = os.path.join(CHECKOUT_ROOT, "share")
