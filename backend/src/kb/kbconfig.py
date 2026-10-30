"""Which knowledge base this process works on: discovery, `kb.toml`, selection.

The explorer is code only. A knowledge base is any folder holding a `kb.toml`; it may be its own git
repository (then every `kb(...)` commit and `kb-x.y.z` tag lands there, see `git_root`). Knowledge bases are
found in two places, merged (registry wins on the same id):

  1. `<bases dir>/kb-<id>/kb.toml` — the bases dir is `$KB_BASES_DIR`, else `<explorer>/../knowledge-bases`.
     Symlinks are followed, so `kb-<id>` may point anywhere on disk.
  2. `<explorer>/knowledge-bases.toml` (gitignored, machine-local): `default = "<id>"` and
     `[[kb]] id = "...", path = "~/anywhere"` entries.

Selection, first hit wins: `--kb <id>` on the command line, `$KB`, the registry's `default`, the only
knowledge base there is. `$KB_ROOT` (legacy, used by the share build) still points straight at a folder.
Nothing here imports the rest of `kb`, so `kb.paths` and `kb.core.schema` can build on it at import time.

    python -m kb.kbconfig list     every knowledge base and where it is
    python -m kb.kbconfig show     the selected one, resolved
    python -m kb.kbconfig root     just its folder (what tools/qmd/with-kb.sh hands node as $KB_ROOT)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

try:
    import tomllib
except ModuleNotFoundError:          # python < 3.11 (the macOS system python running a hook): tomli if present
    try:
        import tomli as tomllib      # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None               # type: ignore[assignment]

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKOUT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CODE_DIR)))
CONFIG_NAME = "kb.toml"
REGISTRY_NAME = "knowledge-bases.toml"
FOLDER_PREFIX = "kb-"
THINK_DIR_NAME = "think"
# `[kb] schema_version` a knowledge base must carry to be opened by this explorer (major.minor of kb-x.y.z).
# Kept here, not in kb.core.schema, so this module stays import-free; the schema asserts both agree.
SCHEMA_VERSION = (1, 3)


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
        d = self.data.get(name)
        return d if isinstance(d, dict) else {}

    @property
    def tag_prefix(self) -> str:
        return str(self.section("git").get("tag_prefix") or "kb-")


def bases_dir() -> str:
    env = os.environ.get("KB_BASES_DIR")
    return os.path.realpath(env) if env else os.path.realpath(os.path.join(CHECKOUT_ROOT, os.pardir, "knowledge-bases"))


def registry_path() -> str:
    return os.path.join(CHECKOUT_ROOT, REGISTRY_NAME)


def _toml_load(f):
    if tomllib is None:
        raise KbConfigError(f"{sys.executable} has no tomllib (python < 3.11) — run through pixi's python")
    return tomllib.load(f)


def _read_registry() -> dict:
    try:
        with open(registry_path(), "rb") as f:
            return _toml_load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise KbConfigError(f"{registry_path()}: TOML syntax error: {e}") from None


def _expand(path: str) -> str:
    return os.path.realpath(os.path.expanduser(os.path.expandvars(path)))


def discover() -> dict[str, str]:
    """id → knowledge base folder, folders first, then the registry (which may override an id)."""
    found: dict[str, str] = {}
    base = bases_dir()
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if not name.startswith(FOLDER_PREFIX):
                continue
            folder = os.path.join(base, name)
            if os.path.isdir(folder) and os.path.isfile(os.path.join(folder, CONFIG_NAME)):
                found[name[len(FOLDER_PREFIX):]] = os.path.realpath(folder)
    for entry in _read_registry().get("kb") or []:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("path"):
            raise KbConfigError(f"{registry_path()}: every [[kb]] needs `id` and `path`")
        found[str(entry["id"])] = _expand(str(entry["path"]))
    return found


def think_root(vault_root: str | None = None) -> str:
    """The shared think space `<bases dir>/think`; a vault's own `think/` only when the shared one is absent."""
    shared = os.path.join(bases_dir(), THINK_DIR_NAME)
    if os.path.isdir(shared) or vault_root is None:
        return shared
    return os.path.join(vault_root, THINK_DIR_NAME)


def _consume_argv_kb() -> str | None:
    """Read `--kb <id>` / `--kb=<id>` from sys.argv once and remove it, so every CLI (lint, ops, ingest, api…)
    accepts it without declaring it. Exported as $KB so child processes see the same choice."""
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
    os.environ["KB"] = pick
    return pick


_ARGV_KB = _consume_argv_kb()


def explicit_kb() -> str | None:
    """The `--kb` given on this command line (not `$KB`): for commands that act on a kb only when asked to."""
    return _ARGV_KB


def selected_id() -> str | None:
    """`--kb`, `$KB`, the registry default, or the only knowledge base; None when nothing decides."""
    pick = _ARGV_KB or os.environ.get("KB")
    if pick:
        return pick
    default = _read_registry().get("default")
    if default:
        return str(default)
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
        raise KbConfigError(f"{path}: [kb] id = {kb_id!r} but the folder/registry calls it {id_hint!r}")
    version = _version(kb["schema_version"], path)
    if version != SCHEMA_VERSION:
        msg = (f"{path}: schema_version {version[0]}.{version[1]} but this explorer speaks "
               f"{SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]} — run `pixi run ops -- migrate` on it")
        if strict:
            raise KbConfigError(msg)
        print(f"warning: {msg}", file=sys.stderr)
    git_root = root if os.path.exists(os.path.join(root, ".git")) else None
    return KbConfig(id=kb_id, name=str(kb["name"]), root=root, path=path, schema_version=version,
                    git_root=git_root, data=data)


def load(kb_id: str, strict: bool = True) -> KbConfig:
    known = discover()
    if kb_id not in known:
        have = ", ".join(sorted(known)) or "none"
        raise KbConfigError(f"no knowledge base {kb_id!r} (known: {have}; bases dir {bases_dir()}, "
                            f"registry {registry_path()})")
    return load_dir(known[kb_id], kb_id, strict=strict)


def register(path: str) -> KbConfig:
    """Save a knowledge base folder in the registry (`[[kb]] id, path`) after checking this explorer can open it:
    a kb.toml at this explorer's schema version, in a folder that is its own git repository. Idempotent."""
    root = _expand(path)
    if not os.path.isdir(root):
        raise KbConfigError(f"{root}: no such folder")
    cfg = load_dir(root, strict=True)
    if cfg.git_root is None:
        raise KbConfigError(f"{root} is not a git repository — a knowledge base is its own repo (git init there first)")
    known = discover()
    if cfg.id in known:
        if os.path.realpath(known[cfg.id]) == cfg.root:
            return cfg
        raise KbConfigError(f"a knowledge base {cfg.id!r} is already known at {known[cfg.id]}")
    import json
    reg = registry_path()
    new = not os.path.isfile(reg) or not os.path.getsize(reg)
    with open(reg, "a", encoding="utf-8") as f:
        if new:
            f.write("# Knowledge bases outside the bases dir (machine-local, gitignored).\n")
        f.write(f"\n[[kb]]\nid = {json.dumps(cfg.id)}\npath = {json.dumps(cfg.root)}\n")
    return cfg


def schema_mismatch(cfg: "KbConfig | None") -> str | None:
    """Lint's view of a version mismatch: the message, or None when the kb matches this explorer."""
    if cfg and cfg.schema_version != SCHEMA_VERSION:
        return (f"kb.toml schema_version {'.'.join(map(str, cfg.schema_version))} ≠ explorer "
                f"{'.'.join(map(str, SCHEMA_VERSION))} — run `pixi run ops -- migrate`")
    return None


_current: KbConfig | None | bool = False   # False = not resolved yet


def current() -> KbConfig | None:
    """The knowledge base this process works on, resolved once. None = legacy mode (no kb.toml anywhere:
    `$KB_ROOT`/the checkout is the vault, types are the explorer defaults)."""
    global _current
    if _current is not False:
        return _current
    env_root = os.environ.get("KB_ROOT")
    if env_root:
        _current = load_dir(env_root, strict=False) if os.path.isfile(os.path.join(env_root, CONFIG_NAME)) else None
        return _current
    kb_id = selected_id()
    if kb_id:
        _current = load(kb_id, strict=False)
    elif os.path.isfile(os.path.join(CHECKOUT_ROOT, CONFIG_NAME)):
        _current = load_dir(CHECKOUT_ROOT, strict=False)
    else:
        _current = None
        known = discover()
        if len(known) > 1 and not os.path.isdir(os.path.join(CHECKOUT_ROOT, "wiki")):
            print(f"warning: {len(known)} knowledge bases ({', '.join(sorted(known))}) and none selected — "
                  f"pass --kb <id> or set KB; using the checkout as the vault (legacy layout)", file=sys.stderr)
    return _current


def vault_root() -> str:
    """`$KB_ROOT`, else the selected knowledge base, else the checkout (legacy monorepo layout)."""
    env_root = os.environ.get("KB_ROOT")
    if env_root:
        return env_root
    kb = current()
    return kb.root if kb else CHECKOUT_ROOT


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
            print(f"no knowledge bases in {bases_dir()} or {registry_path()}")
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
        # Non-Python tools (tools/qmd/*.mjs) get their vault from here, never from where their file lives:
        # an explorer checkout without wiki/ is not a vault, so refuse instead of guessing it.
        if cfg is None and not os.environ.get("KB_ROOT") and not os.path.isdir(os.path.join(CHECKOUT_ROOT, "wiki")):
            print("error: no knowledge base selected — pass --kb <id> or set KB (`pixi run kb-list`)", file=sys.stderr)
            return 1
        print(vault_root())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
