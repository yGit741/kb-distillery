"""Which knowledge base this process works on: discovery, `kb.toml`, selection.

The engine is code only. A knowledge base is a folder holding a `kb.toml`; it may be its own git repository (then every
`kb(...)` commit and `kb-x.y.z` tag lands there, see `git_root`). One discovery path:

  1. `<bases dir>/<id>/kb.toml` — the bases dir is `$KB_DISTILLERY_HOME`, else `~/knowledge` (`$KB_BASES_DIR` replaces
     both, a test override). The folder name is the id. Symlinks are followed.
  2. `--kb <path>` — any folder with a `kb.toml`, anywhere.

`--kb` and `$KB` take an id or a path: a value containing `/` or starting with `.` or `~` is a path, anything else an id.
Selection, first hit wins: `--kb`, `$KB`, the nearest `kb.toml` above the current folder (only outside a checkout), the
only knowledge base there is, then the one named by `[kb] default = "<id>"` in the engine config (`~/.config/kb-distillery/engine.toml`,
`$KB_ENGINE_CONFIG` moves it) when several exist. `$KB_ROOT` is internal: tools set it to hand a resolved folder to the processes they start
(the share build, qmd, hooks); users never do.
Nothing here imports the rest of `kb` (only `kb_distillery.config.resources`, which imports nothing), so
`kb_distillery.config.paths` and `kb_distillery.vault.schema` can build on it at import time. No repository root is computed at
import: an installed wheel has none (see `config/resources.py`).

    python -m kb_distillery.config.kb list     every knowledge base and where it is
    python -m kb_distillery.config.kb show     the selected one, resolved
    python -m kb_distillery.config.kb root     just its folder (what scripts/qmd/with-kb.sh hands node as $KB_ROOT)
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

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the kb_distillery package folder (this file is config/kb.py)
CONFIG_NAME = "kb.toml"
HOME_ENV = "KB_DISTILLERY_HOME"
DEFAULT_HOME = os.path.join("~", "knowledge")
THINK_DIR_NAME = "think"
# `[kb] schema_version` a knowledge base must carry to be opened by this explorer (major.minor of kb-x.y.z).
# Kept here, not in kb_distillery.vault.schema, so this module stays import-free; the schema asserts both agree.
SCHEMA_VERSION = (1, 5)


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
        """A kb.toml table. `[types]` and `[edges]` of a kb that names a kit come back as the kit's tables
        extended by the kb's own (kb_distillery.config.kit); every other table is read as written."""
        d = self.data.get(name)
        d = d if isinstance(d, dict) else {}
        if self.kit and name in ("types", "edges"):
            from kb_distillery.config import kit             # lazy: this module stays import-free
            return kit.section(self.kit, name, d, self.path)
        return d

    @property
    def kit(self) -> str:
        """The kit this kb follows ("" = none, the kb.toml carries its own schema): `[kb] kit`, else the older
        `[kb] template`; the old names `starter` and `academic-research` come back as `base` and `research`."""
        kb = self.data.get("kb")
        raw = str((kb.get("kit") or kb.get("template") or "") if isinstance(kb, dict) else "")
        if not raw:
            return ""
        from kb_distillery.config import kit
        return kit.canonical(raw)

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


def search_dirs() -> list[str]:
    """Every folder searched for `<id>/kb.toml`, first hit wins: the bases dir only (a checkout's own `kbs/` is not
    looked at)."""
    return [bases_dir()]


HOOKS_RESOURCE = "kits/base/hooks"      # the kit folder `hooks_path_for` points git at


def hooks_path_for(kb_root: str) -> str:
    """`core.hooksPath` for a knowledge base repo: the kit's `hooks/` folder (package data, `kits/base/hooks`).

    Relative to the kb (survives renaming the engine folder) when the kb sits inside the engine checkout, i.e. both
    live under the same home (`<engine>/kbs/<id>` -> `../../src/kb_distillery/kits/base/hooks`); absolute otherwise.
    Git resolves a relative value from the top of the work tree, where the hooks run. From a linked worktree the
    primary checkout's copy is used: it outlives the worktree, and a path into a deleted worktree makes git run no
    hooks at all."""
    primary = primary_root()
    home = os.path.realpath(primary) if primary else None
    # in a checkout the package sits at <checkout>/src/kb_distillery, so the primary's copy is the same resource there
    hooks = os.path.join(home, "src", "kb_distillery", *HOOKS_RESOURCE.split("/")) if home \
        else os.path.realpath(str(resources.resource(HOOKS_RESOURCE)))
    root = os.path.realpath(kb_root)
    if home and os.path.commonpath([root, home]) == home and os.path.commonpath([hooks, home]) == home:
        return os.path.relpath(hooks, root)
    return hooks


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


def _anchor_env_kb() -> None:
    """A relative `$KB` path (`KB=./examples/demo`) is resolved once, against the folder the process started in, and
    exported absolute: the guard hook, the pytest subprocesses and every other child may start elsewhere, and a relative
    path would silently point each of them at a different (or no) folder."""
    pick = os.environ.get("KB")
    if pick and looks_like_path(pick):
        os.environ["KB"] = _expand(pick)


_anchor_env_kb()


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


def default_kb() -> str | None:
    """The id in `[kb] default` of the engine config; None when unset, unreadable or not a known knowledge base."""
    cfg = os.environ.get("KB_ENGINE_CONFIG") or os.path.join(os.path.expanduser("~"), ".config", "kb-distillery", "engine.toml")
    try:
        import tomllib
        with open(cfg, "rb") as f:
            section = tomllib.load(f).get("kb")
    except (OSError, ValueError, ImportError):
        return None
    pick = section.get("default") if isinstance(section, dict) else None
    return pick if isinstance(pick, str) and pick in discover() else None


def selected() -> str | None:
    """`--kb`, `$KB`, the kb folder the shell is in, the only knowledge base, or the configured default: an id or a path; None when nothing decides."""
    pick = _ARGV_KB or os.environ.get("KB")
    if pick:
        return pick
    above = kb_above()
    if above:
        return above
    known = discover()
    if len(known) == 1:
        return next(iter(known))
    return default_kb()


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
    from kb_distillery.config import kit
    named = {key: kb[key] for key in ("kit", "template") if kb.get(key) not in (None, "")}
    for key, value in named.items():
        if not isinstance(value, str) or not kit.exists(value):
            raise KbConfigError(f"{path}: [kb] {key} = {value!r} is not a known kit "
                                f"(known: {', '.join(kit.names()) or 'none'}; kits dir {kit.kits_dir()})")
        try:
            kit.chain(value)
        except kit.KitError as e:
            raise KbConfigError(f"{path}: [kb] {key}: {e}") from None
    if len({kit.canonical(v) for v in named.values()}) > 1:
        raise KbConfigError(f"{path}: [kb] kit = {named['kit']!r} and template = {named['template']!r} name different kits "
                            f"(template is the older spelling of kit; keep one)")
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


READ_ONLY_MESSAGE = "this knowledge base is read-only (example kb)"
READ_ONLY_ENV = "KB_READ_ONLY"


class ReadOnlyError(KbConfigError):
    """A write was attempted on a read-only knowledge base."""


def examples_dirs() -> list[str]:
    """The `examples/` folders of this engine checkout (and of its primary working tree, from a linked worktree)."""
    out = []
    for base in (checkout_root(), primary_root()):
        if base:
            path = os.path.realpath(os.path.join(base, "examples"))
            if path not in out:
                out.append(path)
    return out


def is_read_only(root: str | None = None, examples: list[str] | None = None) -> bool:
    """True when the kb at `root` (default: the active one) must not be written: `$KB_READ_ONLY=1`, `[kb] read_only = true`
    in its kb.toml, or its folder lies under the engine's `examples/` (`examples` replaces that list; tests use it)."""
    if os.environ.get(READ_ONLY_ENV) == "1":
        return True
    root = os.path.realpath(root or vault_root())
    for ex in (examples_dirs() if examples is None else [os.path.realpath(e) for e in examples]):
        if root == ex or root.startswith(ex + os.sep):
            return True
    try:
        with open(os.path.join(root, CONFIG_NAME), "rb") as f:
            kb = _toml_load(f).get("kb")
    except (OSError, ValueError):
        return False
    return isinstance(kb, dict) and kb.get("read_only") is True


def require_writable(root: str | None = None) -> None:
    """The one write guard: raises ReadOnlyError (message READ_ONLY_MESSAGE) when the kb is read-only."""
    if is_read_only(root):
        raise ReadOnlyError(READ_ONLY_MESSAGE)


def list_examples() -> dict[str, str]:
    """Example kbs under the engine's `examples/` (a folder holding a kb.toml): name -> folder."""
    found = {}
    for ex in examples_dirs():
        if os.path.isdir(ex):
            for name in sorted(os.listdir(ex)):
                if os.path.isfile(os.path.join(ex, name, CONFIG_NAME)):
                    found.setdefault(name, os.path.join(ex, name))
    return found


def describe(cfg: KbConfig | None) -> dict:
    return {"id": cfg.id if cfg else None, "name": cfg.name if cfg else None, "root": cfg.root if cfg else vault_root(),
            "git_root": cfg.git_root if cfg else None, "config": cfg.path if cfg else None,
            "schema_version": ".".join(map(str, cfg.schema_version)) if cfg else None,
            "think_root": think_root(vault_root()), "read_only": is_read_only(cfg.root if cfg else None)}


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
    if cmd == "open-example":
        name = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else ""
        known = list_examples()
        if name not in known:
            print(f"error: no example kb {name!r} (available: {', '.join(known) or 'none'})", file=sys.stderr)
            return 2
        os.environ["KB"], os.environ[READ_ONLY_ENV] = known[name], "1"
        launch = os.path.join(checkout_root() or "", "scripts", "launch.sh")
        if not os.path.isfile(launch):
            print("error: open-example needs an engine checkout (scripts/launch.sh)", file=sys.stderr)
            return 2
        import subprocess
        return subprocess.call(["bash", launch, *argv[2:]], env=dict(os.environ, KB_PYTHON=os.environ.get("KB_PYTHON") or sys.executable))
    if cmd == "root":
        try:
            cfg = current()
        except KbConfigError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        # Non-Python tools (scripts/qmd/*.mjs) get their vault from here, never from where their file lives:
        # the engine checkout is not a vault, so refuse instead of guessing it.
        if cfg is None and not os.environ.get("KB_ROOT"):
            print("error: no knowledge base selected — pass --kb <id|path> or set KB (`distill kb list`)", file=sys.stderr)
            return 1
        print(vault_root())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
