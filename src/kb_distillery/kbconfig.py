"""Which knowledge base this process works on: discovery, `kb.toml`, selection.

The engine is code only. A knowledge base is a folder holding a `kb.toml`; it may be its own git repository (then every
`kb(...)` commit and `kb-x.y.z` tag lands there, see `git_root`). One discovery path:

  1. `<bases dir>/<id>/kb.toml` — the bases dir is `$KB_DISTILLERY_HOME`, else `~/knowledge` (`$KB_BASES_DIR` replaces
     both, a test override). The folder name is the id. Symlinks are followed. TRANSITIONAL: until the user's kbs move
     to `~/knowledge` (Lane C.6), an id found nowhere there is looked up in the repository's own `kbs/` folder
     (`_transitional_repo_kbs_dirs`, deleted in C.6).
  2. `--kb <path>` — any folder with a `kb.toml`, anywhere.

`--kb` and `$KB` take an id or a path: a value containing `/` or starting with `.` or `~` is a path, anything else an id.
Selection, first hit wins: `--kb`, `$KB`, the nearest `kb.toml` above the current folder (only outside a checkout), the
only knowledge base there is. `$KB_ROOT` is internal: tools set it to hand a resolved folder to the processes they start
(the share build, qmd, hooks); users never do.
Nothing here imports the rest of `kb` (only `kb_distillery.config.resources`, which imports nothing), so
`kb_distillery.paths` and `kb_distillery.core.schema` can build on it at import time. No repository root is computed at
import: an installed wheel has none (see `config/resources.py`).

    python -m kb_distillery.kbconfig list     every knowledge base and where it is
    python -m kb_distillery.kbconfig show     the selected one, resolved
    python -m kb_distillery.kbconfig root     just its folder (what scripts/qmd/with-kb.sh hands node as $KB_ROOT)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from kb_distillery.config import resources

try:
    import tomllib
except ModuleNotFoundError:          # python < 3.11 (the macOS system python running a hook): tomli if present
    try:
        import tomli as tomllib      # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None               # type: ignore[assignment]

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_NAME = "kb.toml"
BASES_DIR_NAME = "kbs"             # the repository's own kbs/ folder (transitional) and the default HOME subfolder name
HOME_ENV = "KB_DISTILLERY_HOME"
DEFAULT_HOME = os.path.join("~", "knowledge")
THINK_DIR_NAME = "think"
# `[kb] schema_version` a knowledge base must carry to be opened by this explorer (major.minor of kb-x.y.z).
# Kept here, not in kb_distillery.core.schema, so this module stays import-free; the schema asserts both agree.
SCHEMA_VERSION = (1, 4)


class KbConfigError(ValueError):
    """kb.toml missing, unreadable or invalid; the message names the file and the key."""


@dataclass(frozen=True)
class KbConfig:
    id: str
    name: str
    root: str                       # the knowledge base folder (absolute, real path)
    path: str                       # its kb.toml
    schema_version: tuple[int, int]
    git_root: str | None            # the folder itself when it is a git repository, else None
    data: dict = field(default_factory=dict, repr=False)

    def section(self, name: str) -> dict:
        """A kb.toml table. `[types]` and `[edges]` of a kb that names a template come back as the template's tables
        extended by the kb's own (kb_distillery.core.template); every other table is read as written."""
        d = self.data.get(name)
        d = d if isinstance(d, dict) else {}
        if self.template and name in ("types", "edges"):
            from kb_distillery.core import template        # lazy: this module stays import-free
            return template.section(self.template, name, d, self.path)
        return d

    @property
    def template(self) -> str:
        """`[kb] template`: the ontology template this kb follows ("" = none, the kb.toml carries its own schema)."""
        kb = self.data.get("kb")
        return str(kb.get("template") or "") if isinstance(kb, dict) else ""

    @property
    def tag_prefix(self) -> str:
        return str(self.section("git").get("tag_prefix") or "kb-")


def checkout_root() -> str | None:
    """The checkout this code runs from (a repository, or a linked worktree of one), None for an installed package."""
    root = resources.repo_root()
    return str(root) if root else None


def primary_root() -> str | None:
    """The engine's main working tree, None for an installed package. From a linked worktree (its `.git` is a file
    naming `<git dir>/worktrees/x`, whose `commondir` points at the shared git dir) that is not the checkout. Read
    without a subprocess because this module is imported by nearly everything."""
    checkout = checkout_root()
    if checkout is None:
        return None
    dot_git = os.path.join(checkout, ".git")
    if os.path.isfile(dot_git):
        try:
            with open(dot_git, encoding="utf-8") as f:
                first = f.readline().strip()
            if first.startswith("gitdir:"):
                git_dir = os.path.realpath(os.path.join(checkout, first[len("gitdir:"):].strip()))
                with open(os.path.join(git_dir, "commondir"), encoding="utf-8") as f:
                    return os.path.dirname(os.path.realpath(os.path.join(git_dir, f.read().strip())))
        except OSError:
            pass
    return checkout


def bases_dir() -> str:
    """Where knowledge bases live: `$KB_BASES_DIR` (tests), else `$KB_DISTILLERY_HOME`, else `~/knowledge`."""
    env = os.environ.get("KB_BASES_DIR")
    if env:
        return os.path.realpath(env)
    return os.path.realpath(os.path.expanduser(os.environ.get(HOME_ENV) or DEFAULT_HOME))


def _transitional_repo_kbs_dirs() -> list[str]:
    """TRANSITIONAL, deleted in Lane C.6 (when kbs/ moves to ~/knowledge): the repository's own `kbs/` folders, searched
    when an id is not under `bases_dir()`. Order is the safety rule: THIS checkout's `kbs/` first (a linked worktree's
    own tracked copy), the primary checkout's only after it, so a bare id used from a worktree never prefers (and so
    never writes into) the primary's copy when the worktree has its own. A kb found only in the primary is used with a
    warning (`_warn_primary`): the thesis kb is untracked and exists only there."""
    out = []
    for root in (checkout_root(), primary_root()):
        d = os.path.join(root, BASES_DIR_NAME) if root else ""
        if d and os.path.isdir(d) and os.path.realpath(d) not in [os.path.realpath(x) for x in out]:
            out.append(d)
    return out


def search_dirs() -> list[str]:
    """Every folder searched for `<id>/kb.toml`, first hit wins. `$KB_BASES_DIR` is exclusive (hermetic tests)."""
    if os.environ.get("KB_BASES_DIR"):
        return [bases_dir()]
    return [bases_dir(), *_transitional_repo_kbs_dirs()]


def _warn_primary(kb_id: str, folder: str) -> None:
    primary, checkout = primary_root(), checkout_root()
    # compare resolved paths: the primary's kbs/<id> may itself be a symlink (the thesis kb can be)
    if primary and checkout and os.path.realpath(primary) != os.path.realpath(checkout) \
            and os.path.realpath(os.path.join(primary, BASES_DIR_NAME, kb_id)) == os.path.realpath(folder):
        print(f"warning: knowledge base {kb_id!r} resolves to the PRIMARY checkout's kbs/ ({folder}) from the linked "
              f"worktree {checkout}; commands that write would change the primary's copy — pass --kb <path> for a "
              f"worktree-local kb", file=sys.stderr)


def hooks_path_for(kb_root: str) -> str:
    """`core.hooksPath` for a knowledge base repo: relative (survives renaming the engine folder) for a kb at
    `<engine>/kbs/<id>`, else the absolute path of `scripts/kb-hooks` (the primary checkout's, else the packaged copy). Git resolves a relative value
    from the top of the work tree, where the hooks run."""
    primary = primary_root()
    if primary and os.path.dirname(os.path.realpath(kb_root)) == os.path.join(os.path.realpath(primary), BASES_DIR_NAME):
        return "../../scripts/kb-hooks"
    packaged = resources.root_resource(os.path.join("scripts", "kb-hooks"))
    # from a linked worktree prefer the primary's copy: it outlives the worktree a kb's core.hooksPath would point into
    return os.path.join(primary, "scripts", "kb-hooks") if primary else str(packaged)


def _toml_load(f):
    if tomllib is None:
        raise KbConfigError(f"{sys.executable} has no tomllib (python < 3.11) — run through pixi's python")
    return tomllib.load(f)


def _expand(path: str) -> str:
    return os.path.realpath(os.path.expanduser(os.path.expandvars(path)))


def looks_like_path(ref: str) -> bool:
    """A `--kb` / `$KB` value is a path when it has a `/` or starts with `.` or `~`, else an id."""
    return os.sep in ref or "/" in ref or ref.startswith((".", "~"))


def discover() -> dict[str, str]:
    """id → knowledge base folder, for every `<dir>/<id>/kb.toml` in `search_dirs()` (the folder name is the id)."""
    found: dict[str, str] = {}
    for base in search_dirs():
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            folder = os.path.join(base, name)
            if name not in found and not name.startswith(".") and os.path.isdir(folder) \
                    and os.path.isfile(os.path.join(folder, CONFIG_NAME)):
                found[name] = os.path.realpath(folder)
    return found


def think_root(vault_root: str | None = None) -> str:
    """The shared think space `<bases dir>/think` (searched like kbs); a vault's own `think/` only when none exists."""
    dirs = search_dirs()
    for d in dirs:
        shared = os.path.join(d, THINK_DIR_NAME)
        if os.path.isdir(shared):
            _warn_primary(THINK_DIR_NAME, shared)
            return shared
    return os.path.join(dirs[0], THINK_DIR_NAME) if vault_root is None else os.path.join(vault_root, THINK_DIR_NAME)


def _consume_argv_kb() -> str | None:
    """Read `--kb <id|path>` / `--kb=<id|path>` from sys.argv once and remove it, so every CLI (lint, ops, ingest,
    api…) accepts it without declaring it. Exported as $KB so child processes see the same choice."""
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--kb" and i + 1 < len(argv):
            pick = argv[i + 1]
            del argv[i:i + 2]
            break
        if a.startswith("--kb="):
            pick = a[len("--kb="):]
            del argv[i]
            break
    else:
        return None
    if looks_like_path(pick):
        pick = _expand(pick)            # children may start elsewhere: hand them a path that opens from anywhere
    os.environ["KB"] = pick
    return pick


_ARGV_KB = _consume_argv_kb()


def explicit_kb() -> str | None:
    """The `--kb` given on this command line (not `$KB`): for commands that act on a kb only when asked to."""
    return _ARGV_KB


def kb_above(start: str | None = None) -> str | None:
    """The nearest folder at or above `start` (default: the current folder) holding a `kb.toml`; None inside a checkout
    of the engine (its repo-relative use is `KB=./examples/demo`) or when there is none."""
    try:
        here = os.path.realpath(start or os.getcwd())
    except OSError:                     # the current folder was deleted under us
        return None
    repo = checkout_root()
    if repo and (here == os.path.realpath(repo) or here.startswith(os.path.realpath(repo) + os.sep)):
        return None
    while True:
        if os.path.isfile(os.path.join(here, CONFIG_NAME)):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def selected() -> str | None:
    """`--kb`, `$KB`, the kb folder the shell is in, or the only knowledge base: an id or a path; None when nothing decides."""
    pick = _ARGV_KB or os.environ.get("KB")
    if pick:
        return pick
    above = kb_above()
    if above:
        return above
    known = discover()
    return next(iter(known)) if len(known) == 1 else None


def _version(text, path) -> tuple[int, int]:
    parts = str(text).split(".")
    if len(parts) < 2 or not all(p.isdigit() for p in parts[:2]):
        raise KbConfigError(f"{path}: [kb] schema_version must be \"x.y\" (got {text!r})")
    return int(parts[0]), int(parts[1])


def load_dir(root: str, id_hint: str | None = None, strict: bool = True) -> KbConfig:
    root = os.path.realpath(root)
    path = os.path.join(root, CONFIG_NAME)
    try:
        with open(path, "rb") as f:
            data = _toml_load(f)
    except FileNotFoundError:
        raise KbConfigError(f"{path} not found — not a knowledge base folder") from None
    except tomllib.TOMLDecodeError as e:
        raise KbConfigError(f"{path}: TOML syntax error: {e}") from None
    kb = data.get("kb")
    if not isinstance(kb, dict):
        raise KbConfigError(f"{path}: missing [kb] table")
    for key in ("id", "name", "schema_version"):
        if not kb.get(key):
            raise KbConfigError(f"{path}: [kb] {key} is required")
    kb_id = str(kb["id"])
    if id_hint and id_hint != kb_id:
        raise KbConfigError(f"{path}: [kb] id = {kb_id!r} but the folder is named {id_hint!r} (folder name = id)")
    version = _version(kb["schema_version"], path)
    if version != SCHEMA_VERSION:
        msg = (f"{path}: schema_version {version[0]}.{version[1]} but this explorer speaks "
               f"{SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]} — run `pixi run ops -- migrate` on it")
        if strict:
            raise KbConfigError(msg)
        print(f"warning: {msg}", file=sys.stderr)
    if kb.get("template") is not None:
        from kb_distillery.core import template
        if not isinstance(kb["template"], str) or not template.exists(kb["template"]):
            raise KbConfigError(f"{path}: [kb] template = {kb['template']!r} is not a known template "
                                f"(known: {', '.join(template.names()) or 'none'}; templates dir {template.templates_dir()})")
    git_root = root if os.path.exists(os.path.join(root, ".git")) else None
    return KbConfig(id=kb_id, name=str(kb["name"]), root=root, path=path, schema_version=version,
                    git_root=git_root, data=data)


def load(ref: str, strict: bool = True) -> KbConfig:
    """A knowledge base by id (a folder of the bases dir) or by path (`./x`, `~/x`, `/abs/x`)."""
    if looks_like_path(ref):
        return load_dir(_expand(ref), strict=strict)
    known = discover()
    if ref not in known:
        have = ", ".join(sorted(known)) or "none"
        raise KbConfigError(f"no knowledge base {ref!r} (known: {have}; bases dir {bases_dir()}) — "
                            f"or pass a folder: --kb ./path")
    _warn_primary(ref, known[ref])
    return load_dir(known[ref], ref, strict=strict)


def schema_mismatch(cfg: "KbConfig | None") -> str | None:
    """Lint's view of a version mismatch: the message, or None when the kb matches this explorer."""
    if cfg and cfg.schema_version != SCHEMA_VERSION:
        return (f"kb.toml schema_version {'.'.join(map(str, cfg.schema_version))} ≠ explorer "
                f"{'.'.join(map(str, SCHEMA_VERSION))} — run `pixi run ops -- migrate`")
    return None


_current: KbConfig | None | bool = False   # False = not resolved yet


def current() -> KbConfig | None:
    """The knowledge base this process works on, resolved once. None = none selected: engine-only commands
    (ship, lanes, the skills lint) run against the checkout and use the default types."""
    global _current
    if _current is not False:
        return _current
    env_root = os.environ.get("KB_ROOT")
    if env_root:
        _current = load_dir(env_root, strict=False) if os.path.isfile(os.path.join(env_root, CONFIG_NAME)) else None
        return _current
    ref = selected()
    if ref:
        _current = load(ref, strict=False)
    else:
        _current = None
        known = discover()
        if len(known) > 1:
            print(f"warning: {len(known)} knowledge bases ({', '.join(sorted(known))}) and none selected — "
                  f"pass --kb <id|path> or set KB; engine-only commands run against the checkout", file=sys.stderr)
    return _current


def vault_root() -> str:
    """`$KB_ROOT`, else the selected knowledge base, else the checkout, else the current folder (none selected:
    engine-only commands)."""
    env_root = os.environ.get("KB_ROOT")
    if env_root:
        return env_root
    kb = current()
    return kb.root if kb else (checkout_root() or os.getcwd())


def describe(cfg: KbConfig | None) -> dict:
    return {"id": cfg.id if cfg else None, "name": cfg.name if cfg else None, "root": cfg.root if cfg else vault_root(),
            "git_root": cfg.git_root if cfg else None, "config": cfg.path if cfg else None,
            "schema_version": ".".join(map(str, cfg.schema_version)) if cfg else None,
            "think_root": think_root(vault_root())}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "show"
    if cmd == "list":
        known = discover()
        if not known:
            print(f"no knowledge bases in {bases_dir()} (pass --kb <path> for one elsewhere)")
            return 1
        for kb_id, root in known.items():
            git = "git" if os.path.exists(os.path.join(root, ".git")) else "   "
            print(f"{kb_id:<20} {git}  {root}")
        return 0
    if cmd == "show":
        try:
            cfg = current()
        except KbConfigError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        for k, v in describe(cfg).items():
            print(f"{k:<16} {v}")
        return 0
    if cmd == "root":
        try:
            cfg = current()
        except KbConfigError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        # Non-Python tools (scripts/qmd/*.mjs) get their vault from here, never from where their file lives:
        # the engine checkout is not a vault, so refuse instead of guessing it.
        if cfg is None and not os.environ.get("KB_ROOT"):
            print("error: no knowledge base selected — pass --kb <id|path> or set KB (`kbd kb-list`)", file=sys.stderr)
            return 1
        print(vault_root())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
