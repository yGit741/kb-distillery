"""Kits: the ontology a knowledge base follows, versioned in the engine, extended (never edited) by the kb.

A kit is `kits/<name>/kit.toml` inside the package (`kb_distillery/kits`). It owns the same tables a kb.toml used to
carry for itself:

    [kit]
    name = "research"                 # the folder name
    version = 1                       # bumped when the kit changes in a way a kb must notice
    extends = "base"                  # optional: the kit whose resources (defaults, skills, hooks) this one builds on
    description = "..."

    [types] ...                       # exactly the kb.toml [types] format (kb_distillery.core.kbtypes)
    [edges] ...                       # exactly the kb.toml [edges] format (kb_distillery.services.cypher.edge_config)

A kb names its kit in `[kb] kit = "<name>"` (`distill init` writes it). The older `[kb] template = "<name>"` is read
too, and the two old names `starter` and `academic-research` resolve to `base` and `research`, so a kb.toml written
before the rename keeps working. Its own `[types]` / `[edges]` tables then EXTEND the kit's: tables merge key by key,
lists are unioned (the kit's entries first), and a kb value that differs from what the kit already says is an edit, so
it is refused with the table and key named. A kb without a kit keeps reading only its own kb.toml. The merge lives in
`KbConfig.section`, so every reader of `[types]` and `[edges]` sees the same result.

`extends` is validated (the parent must exist, no cycle) and is what later steps use to layer a kit's resources over
its parent's. It does NOT merge the parent's `[types]` / `[edges]` into the child's: a kit's ontology is exactly the
tables in its own kit.toml, so `research` types exactly what `academic-research` did.

The kits folder is `$KB_KITS_DIR` (tests, a second kits folder) or the package's own `kits/`.

Reserved for later phases (rejected in a kit.toml until a phase gives them a meaning): lint rules, views, migrations,
samples. A kit's page skeletons and docs live beside it in `kits/<name>/defaults/`.
"""
from __future__ import annotations

import copy
import os
import tomllib
from functools import lru_cache

from kb_distillery.config.resources import resource

OWNED = ("types", "edges")                 # the kb.toml tables a kit owns
ALLOWED = {"kit", *OWNED}                  # every top-level table a kit.toml may hold today
KITS_DIR_ENV = "KB_KITS_DIR"
KIT_FILE = "kit.toml"
LEGACY_NAMES = {"starter": "base", "academic-research": "research"}      # the names a kb.toml `template =` may still use


class KitError(ValueError):
    """A kit is missing or invalid, or a kb edits what it may only extend; the message names file and key."""


def kits_dir() -> str:
    """`$KB_KITS_DIR` or the package's own `kits` folder (`kb_distillery/kits`, in a checkout and in a wheel alike)."""
    return os.environ.get(KITS_DIR_ENV) or str(resource("kits"))


def _is_name(name: str) -> bool:
    return bool(name) and os.sep not in name and "/" not in name and not name.startswith(".")


def path_of(name: str) -> str:
    return os.path.join(kits_dir(), canonical(name), KIT_FILE)


def _has_file(name: str) -> bool:
    return _is_name(name) and os.path.isfile(os.path.join(kits_dir(), name, KIT_FILE))


def canonical(name: str) -> str:
    """The kit's current name: `starter` -> `base`, `academic-research` -> `research` (unless a kit of the old name is
    really there, as in a test kits folder); any other name as given."""
    return LEGACY_NAMES.get(name, name) if not _has_file(name) else name


def exists(name: str) -> bool:
    return _has_file(canonical(name))


def names() -> list[str]:
    base = kits_dir()
    return sorted(d for d in os.listdir(base) if _has_file(d)) if os.path.isdir(base) else []


@lru_cache(maxsize=32)
def _read(path: str, mtime_ns: int) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise KitError(f"{path}: TOML syntax error: {e}") from None


def load(name: str) -> dict:
    """The kit's tables as read (`kit`, `types`, `edges`), validated."""
    name = canonical(name)
    if not exists(name):
        raise KitError(f"no kit {name!r} (known: {', '.join(names()) or 'none'}; kits dir {kits_dir()})")
    path = path_of(name)
    data = _read(path, os.stat(path).st_mtime_ns)
    meta = data.get("kit")
    if not isinstance(meta, dict) or str(meta.get("name")) != name or not meta.get("version"):
        raise KitError(f"{path}: [kit] needs name = {name!r} (the folder name) and a version")
    if "extends" in meta and not (isinstance(meta["extends"], str) and _is_name(meta["extends"])):
        raise KitError(f"{path}: [kit] extends must name another kit")
    unknown = sorted(set(data) - ALLOWED)
    if unknown:
        raise KitError(f"{path}: unknown table(s) {unknown} (a kit may hold {sorted(ALLOWED)} for now)")
    for table in OWNED:
        if table in data and not isinstance(data[table], dict):
            raise KitError(f"{path}: [{table}] must be a table")
    return data


def chain(name: str) -> list[str]:
    """The kit and the kits it extends, root first (`["base", "research"]`). Raises KitError for a missing parent or a cycle."""
    out: list[str] = []
    current = canonical(name)
    while True:
        if current in out:
            raise KitError(f"kit {current!r} extends itself: {' -> '.join([*reversed(out), current])}")
        meta = load(current)["kit"]
        out.append(current)
        parent = meta.get("extends")
        if not parent:
            return list(reversed(out))
        parent = canonical(str(parent))
        if not exists(parent):
            raise KitError(f"{path_of(current)}: [kit] extends = {parent!r} is not a known kit (known: {', '.join(names()) or 'none'})")
        current = parent


def version(name: str) -> int:
    return int(load(name)["kit"]["version"])


def extend(base, extra, where: str):
    """`extra` (the kb's) laid over `base` (the kit's) without changing anything `base` already says.

    Tables merge key by key, lists are unioned with the kit's entries first, an equal value is fine, and any
    other value for a key the kit has is an edit. `where` names the table in the error."""
    if isinstance(base, dict) and isinstance(extra, dict):
        out = dict(base)
        for key, value in extra.items():
            out[key] = extend(base[key], value, f"{where}.{key}") if key in base else value
        return out
    if isinstance(base, list) and isinstance(extra, list):
        return list(base) + [v for v in extra if v not in base]
    if base == extra:
        return base
    raise KitError(f"{where}: the kit sets {base!r} and kb.toml gives {extra!r}; "
                   f"a kb may add to its kit, not edit it")


def section(name: str, table: str, own: dict, where: str) -> dict:
    """The kb's `table` (`types` / `edges`) as the engine reads it: the kit's, extended by `own`."""
    return copy.deepcopy(extend(load(name).get(table, {}), own, f"{where} [{table}]"))
