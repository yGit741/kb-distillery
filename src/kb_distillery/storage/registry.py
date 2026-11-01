"""Which connectors exist and which one a kb uses.

A kb picks one in kb.toml (none given = the built-in local folder, as before):

    [storage]
    connector = "local-folder"        # a built-in name, or one a package registers (see below)
    [storage.options]                 # passed to the connector as keyword arguments, after the kb root
    # root = "..."

A package adds a connector by exposing a `kb_distillery.storage.base.Connector` subclass in the `kb_distillery.storage.connectors`
entry-point group (pyproject: `[project.entry-points."kb_distillery.storage.connectors"] my-store = "my_pkg.store:MyStore"`).
A package cannot take a built-in name.
"""
from __future__ import annotations

import importlib
from importlib import metadata

from kb_distillery import kbconfig

from .base import Connector, StorageError

GROUP = "kb_distillery.storage.connectors"
DEFAULT = "local-folder"
BUILTIN = {"local-folder": "kb_distillery.storage.localfolder:LocalFolder", "gdrive": "kb_distillery.storage.gdrive:GDrive"}


def _entry_points() -> dict:
    """{name: 'module:Class'} for the installed packages' connectors. One place to patch in tests."""
    return {ep.name: ep.value for ep in metadata.entry_points(group=GROUP)}


def _available() -> dict:
    third = {n: v for n, v in _entry_points().items() if n not in BUILTIN}
    return {**third, **BUILTIN}


def connector_names() -> list[str]:
    return sorted(_available())


def load_class(name: str) -> type[Connector]:
    spec = _available().get(name)
    if spec is None:
        raise StorageError(f"no storage connector {name!r} (known: {', '.join(connector_names())})")
    module, _, attr = spec.partition(":")
    try:
        cls = getattr(importlib.import_module(module), attr)
    except (ImportError, AttributeError) as e:
        raise StorageError(f"storage connector {name!r} ({spec}) could not be loaded: {e}") from None
    if not (isinstance(cls, type) and issubclass(cls, Connector)):
        raise StorageError(f"storage connector {name!r} ({spec}) is not a kb_distillery.storage.Connector subclass")
    return cls


def for_kb(cfg: "kbconfig.KbConfig | None" = None, root: str | None = None) -> Connector:
    """The connector a kb's raw sources live behind. `cfg` None = the kb this process works on; `root` overrides
    the kb folder (a kb with no kb.toml, a test folder)."""
    cfg = cfg if cfg is not None else kbconfig.current()
    section = cfg.section("storage") if cfg else {}
    name = str(section.get("connector") or DEFAULT)
    options = section.get("options") or {}
    if not isinstance(options, dict):
        raise StorageError("[storage.options] must be a table")
    where = root or (cfg.root if cfg else None)
    if not where:
        raise StorageError("no knowledge base selected: pass a kb or a root folder")
    return load_class(name)(where, **options)
