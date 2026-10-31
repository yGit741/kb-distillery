"""Ontology templates: the schema a knowledge base follows, versioned in the engine, extended (never edited) by the kb.

A template is `templates/<name>/template.toml`. It owns the same tables a kb.toml used to carry for itself:

    [template]
    name = "academic-research"        # the folder name
    version = 1                       # bumped when the template changes in a way a kb must notice
    description = "..."

    [types] ...                       # exactly the kb.toml [types] format (kb.core.kbtypes)
    [edges] ...                       # exactly the kb.toml [edges] format (kb.services.cypher.edge_config)

A kb names its template in `[kb] template = "<name>"`. Its own `[types]` / `[edges]` tables then EXTEND the template's:
tables merge key by key, lists are unioned (the template's entries first), and a kb value that differs from what the
template already says is an edit, so it is refused with the table and key named. A kb without `template` keeps
reading only its own kb.toml, as before. The merge lives in `KbConfig.section`, so every reader of `[types]` and
`[edges]` sees the same result and none of them depends on import order.

Reserved for later phases (rejected in a template.toml until a phase gives them a meaning): lint rules,
skills/prompts, views, migrations, samples. Page skeletons move here from meta-defaults/templates in Phase 2.
"""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache

from kb import kbconfig

OWNED = ("types", "edges")                 # the kb.toml tables a template owns
ALLOWED = {"template", *OWNED}             # every top-level table a template.toml may hold today
TEMPLATES_DIR_NAME = "templates"


class TemplateError(ValueError):
    """A template is missing or invalid, or a kb edits what it may only extend; the message names file and key."""


def templates_dir() -> str:
    """`$KB_TEMPLATES_DIR` (tests, a second templates folder) or `<engine checkout>/templates`."""
    return os.environ.get("KB_TEMPLATES_DIR") or os.path.join(kbconfig.CHECKOUT_ROOT, TEMPLATES_DIR_NAME)


def path_of(name: str) -> str:
    return os.path.join(templates_dir(), name, "template.toml")


def exists(name: str) -> bool:
    return bool(name) and os.sep not in name and not name.startswith(".") and os.path.isfile(path_of(name))


def names() -> list[str]:
    base = templates_dir()
    return sorted(d for d in os.listdir(base) if exists(d)) if os.path.isdir(base) else []


@lru_cache(maxsize=32)
def _read(path: str, mtime_ns: int) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise TemplateError(f"{path}: TOML syntax error: {e}") from None


def load(name: str) -> dict:
    """The template's tables as read (`template`, `types`, `edges`), validated."""
    if not exists(name):
        raise TemplateError(f"no template {name!r} (known: {', '.join(names()) or 'none'}; templates dir {templates_dir()})")
    path = path_of(name)
    data = _read(path, os.stat(path).st_mtime_ns)
    meta = data.get("template")
    if not isinstance(meta, dict) or str(meta.get("name")) != name or not meta.get("version"):
        raise TemplateError(f"{path}: [template] needs name = {name!r} (the folder name) and a version")
    unknown = sorted(set(data) - ALLOWED)
    if unknown:
        raise TemplateError(f"{path}: unknown table(s) {unknown} (a template may hold {sorted(ALLOWED)} for now)")
    for table in OWNED:
        if table in data and not isinstance(data[table], dict):
            raise TemplateError(f"{path}: [{table}] must be a table")
    return data


def version(name: str) -> int:
    return int(load(name)["template"]["version"])


def extend(base, extra, where: str):
    """`extra` (the kb's) laid over `base` (the template's) without changing anything `base` already says.

    Tables merge key by key, lists are unioned with the template's entries first, an equal value is fine, and any
    other value for a key the template has is an edit. `where` names the table in the error."""
    if isinstance(base, dict) and isinstance(extra, dict):
        out = dict(base)
        for key, value in extra.items():
            out[key] = extend(base[key], value, f"{where}.{key}") if key in base else value
        return out
    if isinstance(base, list) and isinstance(extra, list):
        return list(base) + [v for v in extra if v not in base]
    if base == extra:
        return base
    raise TemplateError(f"{where}: the template sets {base!r} and kb.toml gives {extra!r}; "
                        f"a kb may add to its template, not edit it")


def section(name: str, table: str, own: dict, where: str) -> dict:
    """The kb's `table` (`types` / `edges`) as the engine reads it: the template's, extended by `own`."""
    return extend(load(name).get(table, {}), own, f"{where} [{table}]")
