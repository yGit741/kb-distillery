"""Where the vault is, and where everything in it lives. The ONE resolver.

`vault_root()` is the vault (content) checkout: `$KB_ROOT` when set (the share build points it at an
archived content ref), else the checkout this code runs from. Every module reads paths from here instead
of recomputing them from `__file__`. Data paths are absolute constants built from the schema's
repo-relative names (`kb_distillery.config.layout`, which the schema re-exports), so renaming a vault folder is
one edit there.

Layout (code vs vault): code lives in `src/kb_distillery`; vault metadata (corpus.tsv, chats/,
templates/, migration state) stays in `meta/`.
"""
import os

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import layout
from kb_distillery.config.resources import resource, root_resource

CODE_DIR = kbconfig.CODE_DIR                                                 # the installed kb_distillery package folder
# There is no import-time checkout root: an installed wheel has none. Code that works on the repository (ship, flags
# codegen, repo lint, the web/ sources) calls `kb_distillery.config.resources.require_repo_root()`; package data is
# found with `resource()` below.


def vault_root():
    """The vault (one knowledge base): $KB_ROOT, else the selected knowledge base (`kb_distillery.config.kb`: `--kb`, $KB,
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


def _kit_defaults(root=None):
    """The `defaults/` folders of the kb's kit chain, the kit itself first, the root kit last (base's is
    META_DEFAULTS_PATH and is always the final fallback). Empty for a kb without a kit."""
    cfg = KB
    if root is not None and os.path.realpath(root) != os.path.realpath(ROOT):
        try:
            cfg = kbconfig.load_dir(root, strict=False) if os.path.isfile(os.path.join(root, kbconfig.CONFIG_NAME)) else None
        except kbconfig.KbConfigError:
            cfg = None
    if cfg is None or not cfg.kit:
        return []
    from kb_distillery.config import kit                  # lazy, like KbConfig.section
    return [os.path.join(kit.kits_dir(), name, "defaults") for name in reversed(kit.chain(cfg.kit))]


def meta_file(*parts, root=None):
    """`meta/<x>` from the knowledge base when it has one, else the first of its kit chain's `defaults/<x>` (the kit
    itself, then the kits it extends), else the base kit's (flags.toml, docs/, templates/, digest/). Resolved per
    file, so a kit carries only the files it changes. Returns the kb path when none exists, so writes land there."""
    own = os.path.join(root or ROOT, "meta", *parts)
    if os.path.exists(own):
        return own
    for base in [*_kit_defaults(root), META_DEFAULTS_PATH]:
        default = os.path.join(base, *parts)
        if os.path.exists(default):
            return default
    return own


def think_path(rel):
    """`think/<file>` (repo-relative spelling) → absolute path in the shared think space."""
    rel = rel.replace("\\", "/")
    if rel.startswith("think/"):
        rel = rel[len("think/"):]
    return os.path.join(THINK_PATH, rel)


# --- vault content ---------------------------------------------------------------------------------
WIKI_PATH = vpath(layout.WIKI_DIR)
RAW_PATH = vpath(layout.RAW_DIR)
# Think is ONE shared human space for every knowledge base (`kbs/think/`, its own repo); a vault's own think/
# only when that is absent. Repo-relative think paths are spelled `think/<file>` everywhere.
THINK_PATH = kbconfig.think_root(ROOT)
INDEX_PATH = vpath(layout.INDEX_REL)
QUARANTINE_PATH = vpath(layout.QUARANTINE_DIR)

# --- vault metadata (meta/) ---------------------------------------------------------------------------
MANIFEST_PATH = vpath(layout.MANIFEST)
LOG_PATH = vpath(layout.LOG_REL)
ALIASES_PATH = vpath("meta", "aliases.tsv")
COHERENCE_PATH = vpath("meta", "coherence-warnings.tsv")
RAW_RENAMES_PATH = vpath("meta", "raw-renames.tsv")
CHATS_PATH = vpath("meta", "chats")
DIGEST_INSTRUCTIONS_PATH = vpath("digest") if os.path.isdir(vpath("digest")) else os.path.join(META_DEFAULTS_PATH, "digest")
MIGRATIONS_APPLIED_PATH = vpath("meta", "migrations", "applied.tsv")

# --- runtime state (gitignored) -------------------------------------------------------------------------
OPS_PATH = vpath(layout.OPS_DIR)
INGEST_PATH = vpath(layout.INGEST_DIR)
DISTILL_PATH = vpath(layout.DISTILL_DIR)
CATALOG_PATH = vpath("meta", ".catalog")
SEMFIND_PATH = vpath("meta", ".semfind")
RESEARCHER_PATH = vpath("meta", ".researcher")
MIGRATE_PATH = vpath("meta", ".migrate")
CACHE_PATH = vpath(".cache")
EXPORT_PATH = vpath(".exported")

# --- code-side resources (package data, found through kb_distillery.config.resources) -------------------------
SKILLS_PATH = str(resource("kits/base/skills"))     # the base kit's skills (every kit has its own kits/<kit>/skills)
TOOLS_PATH = str(root_resource("scripts"))          # a checkout only: the wheel ships none of scripts/
PROMPTS_PATH = str(resource("llm/prompts"))
MIGRATIONS_CODE_PATH = str(resource("migrations"))
SHARE_WORKER_PATH = str(resource("publish/cloudflare/worker"))
