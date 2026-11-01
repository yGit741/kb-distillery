"""Where the vault is, and where everything in it lives. The ONE resolver.

`vault_root()` is the vault (content) checkout: `$KB_ROOT` when set (the share build points it at an
archived content ref), else the checkout this code runs from. Every module reads paths from here instead
of recomputing them from `__file__`. Data paths are absolute constants built from the schema's
repo-relative names (`kb_distillery.core.schema`), so renaming a vault folder is one edit in the schema.

Layout (code vs vault): code lives in `src/kb_distillery`; vault metadata (corpus.tsv, log.md, chats/,
templates/, migration state) stays in `meta/`.
"""
import os

from kb_distillery import kbconfig
from kb_distillery.config.resources import resource, root_resource

CODE_DIR = kbconfig.CODE_DIR                                                 # the installed kb_distillery package folder
# There is no import-time checkout root: an installed wheel has none. Code that works on the repository (ship, flags
# codegen, repo lint, the web/ sources) calls `kb_distillery.config.resources.require_repo_root()`; package data is
# found with `resource()` below.


def vault_root():
    """The vault (one knowledge base): $KB_ROOT, else the selected knowledge base (`kb_distillery.kbconfig`: `--kb`, $KB,
    the only one), else the checkout this code runs from (none selected: engine-only commands)."""
    return kbconfig.vault_root()


ROOT = vault_root()
KB = kbconfig.current()                    # the knowledge base's kb.toml, or None when none is selected
# A knowledge base that is a plain folder (no .git, like examples/demo inside the engine repo) must never make git walk
# up into an enclosing repository: every git call this process or its children make stops at these parents.
# Never add the bases dir's parent (the engine itself): git would stop before it and lose the engine's own repo.
os.environ.setdefault("GIT_CEILING_DIRECTORIES", os.pathsep.join(sorted({
    os.path.dirname(os.path.realpath(ROOT)),
    *([os.path.dirname(os.path.realpath(kbconfig.checkout_root()))] if kbconfig.checkout_root() else [])})))
META_DIR = os.path.join(ROOT, "meta")      # vault metadata only (no code lives here any more)
META_DEFAULTS_PATH = str(resource("kits/base/defaults"))   # the base kit's defaults (flags, docs, page skeletons, digest) a kb's meta/ overrides


def vpath(*parts, root=None):
    """A path inside the vault: vpath("wiki", "x.md")."""
    return os.path.join(root or ROOT, *parts)


def meta_file(*parts, root=None):
    """`meta/<x>` from the knowledge base when it has one, else the base kit's `defaults/<x>`
    (flags.toml, docs/, templates/, digest/). Returns the kb path when neither exists, so writes land there."""
    own = os.path.join(root or ROOT, "meta", *parts)
    if os.path.exists(own):
        return own
    default = os.path.join(META_DEFAULTS_PATH, *parts)
    return default if os.path.exists(default) else own


def think_path(rel):
    """`think/<file>` (repo-relative spelling) → absolute path in the shared think space."""
    rel = rel.replace("\\", "/")
    if rel.startswith("think/"):
        rel = rel[len("think/"):]
    return os.path.join(THINK_PATH, rel)


def _rel(name, default):
    try:
        from kb_distillery.core import schema
        return getattr(schema, name, default)
    except Exception:       # schema not importable (bootstrap): fall back to the documented name
        return default


# --- vault content ---------------------------------------------------------------------------------
WIKI_PATH = vpath(_rel("WIKI_DIR", "wiki"))
RAW_PATH = vpath(_rel("RAW_DIR", "raw"))
# Think is ONE shared human space for every knowledge base (`kbs/think/`, its own repo); a vault's own think/
# only when that is absent. Repo-relative think paths are spelled `think/<file>` everywhere.
THINK_PATH = kbconfig.think_root(ROOT)
INDEX_PATH = vpath("index.md")
QUARANTINE_PATH = vpath(_rel("QUARANTINE_DIR", "_quarantine"))

# --- vault metadata (meta/) ---------------------------------------------------------------------------
MANIFEST_PATH = vpath(_rel("MANIFEST", "meta/corpus.tsv"))
LOG_PATH = vpath("meta", "log.md")
ALIASES_PATH = vpath("meta", "aliases.tsv")
COHERENCE_PATH = vpath("meta", "coherence-warnings.tsv")
RAW_RENAMES_PATH = vpath("meta", "raw-renames.tsv")
CHATS_PATH = vpath("meta", "chats")
TEMPLATES_PATH = meta_file("templates")
DIGEST_INSTRUCTIONS_PATH = vpath("digest") if os.path.isdir(vpath("digest")) else os.path.join(META_DEFAULTS_PATH, "digest")
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

# --- code-side resources (package data, found through kb_distillery.config.resources) -------------------------
SKILLS_PATH = str(root_resource("skills"))
TOOLS_PATH = str(root_resource("scripts"))          # a checkout only: the wheel ships scripts/kb-hooks, not the rest
PROMPTS_PATH = str(resource("prompts"))
MIGRATIONS_CODE_PATH = str(resource("migrations"))
SHARE_WORKER_PATH = str(root_resource("share"))
