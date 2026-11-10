"""Kits: the ontology a knowledge base follows, versioned in the engine, extended (never edited) by the kb.

A kit is `kits/<name>/kit.toml` inside the package (`kb_distillery/kits`). It owns the same tables a kb.toml used to
carry for itself:

    [kit]
    name = "research"                 # the folder name
    version = 1                       # bumped when the kit changes in a way a kb must notice
    extends = "base"                  # optional: the kit whose resources (defaults, skills, hooks) this one builds on
    description = "..."

    [types] ...                       # exactly the kb.toml [types] format (kb_distillery.vault.kbtypes)
    [edges] ...                       # exactly the kb.toml [edges] format (kb_distillery.graph.model.edge_config)
    [pages] ...                       # page conventions: takeaways_heading, focus_slugs (kb_distillery.config.pages)
    [agent] skills = ["deep-research"]   # app skills the chat agent may use; a kb.toml [agent] skills replaces it

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

An installed package adds a kit through the `kb_distillery.kits` entry-point group (`my-kit = "my_pkg.kit"`: a
package whose folder holds `kit.toml`, plus the skills, defaults and views folders of a built-in one) and a loose skill
through `kb_distillery.skills` (`my-skill = "my_pkg.skill"`: a package whose folder holds `SKILL.md`). A built-in
name always wins. See docs/guides/build-an-extension.md.

Ready views are files, not a kit.toml table: `kits/<name>/views/*.toml` (see `views()`).

Reserved for later phases (rejected in a kit.toml until a phase gives them a meaning): lint rules, migrations, samples. A kit's page skeletons and docs live beside it in `kits/<name>/defaults/`; a kit that extends another carries
only the files it changes (`kb_distillery.config.paths.meta_file` looks child kit first, then up the chain).
"""
from __future__ import annotations

import copy
import importlib.util
import os
import tomllib
from functools import lru_cache
from importlib import metadata

from kb_distillery.config.resources import resource

OWNED = ("types", "edges")                 # the kb.toml tables a kit owns
PAGES = "pages"                            # page conventions (takeaways heading, focus pages): kb_distillery.config.pages
AGENT = "agent"                            # chat-agent defaults: `skills` (the app skills it may use), see kb_distillery.services.agent_skills
ALLOWED = {"kit", PAGES, AGENT, *OWNED}           # every top-level table a kit.toml may hold today
KITS_DIR_ENV = "KB_KITS_DIR"
KITS_GROUP = "kb_distillery.kits"           # entry-point group: kit name -> a package folder holding kit.toml
SKILLS_GROUP = "kb_distillery.skills"       # entry-point group: skill name -> a package folder holding SKILL.md
KIT_FILE = "kit.toml"
KB_DOCS = ("page-model", "kits", "publish", "storage", "raw-and-corpus", "collections", "think", "workflows",
           "semantic-lint")      # the docs a kb's AGENTS.md routes to; `distill init` copies them to its `.claude/docs/`
LEGACY_NAMES = {"starter": "base", "academic-research": "research"}      # the names a kb.toml `template =` may still use


class KitError(ValueError):
    """A kit is missing or invalid, or a kb edits what it may only extend; the message names file and key."""


def kits_dir() -> str:
    """`$KB_KITS_DIR` or the package's own `kits` folder (`kb_distillery/kits`, in a checkout and in a wheel alike)."""
    return os.environ.get(KITS_DIR_ENV) or str(resource("kits"))


def _is_name(name: str) -> bool:
    return bool(name) and os.sep not in name and "/" not in name and not name.startswith(".")


def _entry_points(group: str) -> dict:
    """{name: 'module[:attr]'} for the installed packages in `group`. One place to patch in tests."""
    try:
        return {ep.name: ep.value for ep in metadata.entry_points(group=group)}
    except Exception:                       # a corrupt installed dist must not break every kb
        return {}


def _package_dir(spec_value: str) -> str | None:
    """The folder of the package an entry-point value names (`my_pkg.kit` or `my_pkg.kit:attr`).

    The module itself is not run, but a dotted name imports its parent packages; any error there skips the package.
    """
    module = spec_value.partition(":")[0].strip()
    try:
        spec = importlib.util.find_spec(module)
    except Exception:                       # a third-party __init__ that raises must not break every kb
        return None
    if spec is None:
        return None
    if spec.submodule_search_locations:
        return next(iter(spec.submodule_search_locations), None)
    return os.path.dirname(spec.origin) if spec.origin else None


def _extension_dirs(group: str, marker: str) -> dict[str, str]:
    """name -> folder for the installed extensions of `group` whose folder holds `marker`; a broken one is skipped."""
    out: dict[str, str] = {}
    for name, value in sorted(_entry_points(group).items()):
        folder = _package_dir(value) if _is_name(name) else None
        if folder and os.path.isfile(os.path.join(folder, marker)):
            out[name] = folder
    return out


def _has_file(name: str) -> bool:
    return _is_name(name) and os.path.isfile(os.path.join(kits_dir(), name, KIT_FILE))


def canonical(name: str) -> str:
    """The kit's current name: `starter` -> `base`, `academic-research` -> `research` (unless a kit of the old name is
    really there, as in a test kits folder); any other name as given."""
    return LEGACY_NAMES.get(name, name) if not _has_file(name) else name


def kit_dir(name: str) -> str:
    """The folder of kit `name`: the kits folder's own, else an installed package's (entry-point group `kb_distillery.kits`).
    A built-in name cannot be taken by a package. Returns the kits-folder path when neither exists."""
    name = canonical(name)
    own = os.path.join(kits_dir(), name)
    if _has_file(name) or not _is_name(name):
        return own
    return _extension_dirs(KITS_GROUP, KIT_FILE).get(name, own)


def skill_dirs() -> dict[str, str]:
    """skill name -> folder, for the skills installed packages add (entry-point group `kb_distillery.skills`)."""
    return _extension_dirs(SKILLS_GROUP, "SKILL.md")


def path_of(name: str) -> str:
    return os.path.join(kit_dir(name), KIT_FILE)


def exists(name: str) -> bool:
    name = canonical(name)
    return _has_file(name) or name in _extension_dirs(KITS_GROUP, KIT_FILE)


def names() -> list[str]:
    base = kits_dir()
    own = {d for d in os.listdir(base) if _has_file(d)} if os.path.isdir(base) else set()
    return sorted(own | set(_extension_dirs(KITS_GROUP, KIT_FILE)))


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
    for table in (*OWNED, PAGES):
        if table in data and not isinstance(data[table], dict):
            raise KitError(f"{path}: [{table}] must be a table")
    agent = data.get(AGENT, {})
    if not isinstance(agent, dict):
        raise KitError(f"{path}: [agent] must be a table")
    if "skills" in agent and not (isinstance(agent["skills"], list) and all(isinstance(x, str) for x in agent["skills"])):
        raise KitError(f"{path}: [agent] skills must be a list of skill names")
    pages = data.get(PAGES, {})
    if "takeaways_heading" in pages and not (isinstance(pages["takeaways_heading"], str) and pages["takeaways_heading"].strip()):
        raise KitError(f"{path}: [pages] takeaways_heading must be a non-empty string")
    if "focus_slugs" in pages and not (isinstance(pages["focus_slugs"], list) and all(isinstance(x, str) for x in pages["focus_slugs"])):
        raise KitError(f"{path}: [pages] focus_slugs must be a list of slugs")
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


VIEWS_DIR = "views"


def views(name: str) -> list[dict]:
    """The ready views of a kit and the kits it extends (`kits/<kit>/views/*.toml`, `[[view]]` tables), root kit first.

    Each view is `id`, `name`, `description` (one plain line) and `layers`: a list of lines of the graph's query
    language, parsed by the frontend only. A child kit's view with the same id replaces its parent's in place.
    Returns dicts with those keys plus `kit` (the kit that ships it). Raises KitError for a malformed file.
    """
    out: dict[str, dict] = {}
    for kit in chain(name):
        folder = os.path.join(kit_dir(kit), VIEWS_DIR)
        if not os.path.isdir(folder):
            continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(".toml"):
                continue
            path = os.path.join(folder, fname)
            try:
                with open(path, "rb") as fh:
                    data = tomllib.load(fh)
            except tomllib.TOMLDecodeError as e:
                raise KitError(f"{path}: TOML syntax error: {e}") from None
            items = data.get("view", [])
            if not isinstance(items, list):
                raise KitError(f"{path}: `view` must be an array of tables ([[view]])")
            for item in items:
                if not isinstance(item, dict):
                    raise KitError(f"{path}: each [[view]] must be a table")
                for key in ("id", "name", "description"):
                    if not (isinstance(item.get(key), str) and item[key].strip()):
                        raise KitError(f"{path}: [[view]] needs a non-empty string `{key}`")
                lines = item.get("layers")
                if not (isinstance(lines, list) and lines and all(isinstance(x, str) and x.strip() for x in lines)):
                    raise KitError(f"{path}: view {item['id']!r} needs `layers`, a non-empty list of lines")
                out[item["id"]] = {"id": item["id"], "name": item["name"].strip(), "description": item["description"].strip(),
                                   "layers": [x.strip() for x in lines], "kit": kit}
    return list(out.values())
