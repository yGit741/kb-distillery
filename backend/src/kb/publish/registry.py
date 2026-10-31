"""Which publishers exist and which one a kb uses.

A kb picks one in kb.toml; the engine default is `$KB_PUBLISHER`; neither = no publisher (`NullPublisher`):

    [publish]
    publisher = "cloudflare"          # a built-in name, or one a package registers (see below)
    [publish.options]                 # passed to the publisher as keyword arguments, after the kb root

A package adds a publisher by exposing a `kb.publish.Publisher` subclass in the `kb.publishers` entry-point group
(pyproject: `[project.entry-points."kb.publishers"] my-host = "my_pkg.host:MyHost"`). A package cannot take a built-in
name. Importing this module never imports a publisher's code: that happens when it is selected.
"""
from __future__ import annotations

import importlib
import os
from importlib import metadata
from typing import Optional

from kb import kbconfig

from .base import Publisher, PublishError
from .null import NullPublisher

GROUP = "kb.publishers"
ENV = "KB_PUBLISHER"
NONE_NAMES = ("", "none", "null")
BUILTIN: dict[str, str] = {}


def _entry_points() -> dict:
    """{name: 'module:Class'} for the installed packages' publishers. One place to patch in tests."""
    return {ep.name: ep.value for ep in metadata.entry_points(group=GROUP)}


def _available() -> dict:
    third = {n: v for n, v in _entry_points().items() if n not in BUILTIN and n not in NONE_NAMES}
    return {**third, **BUILTIN}


def publisher_names() -> list[str]:
    return sorted(_available())


def load_class(name: str) -> type[Publisher]:
    spec = _available().get(name)
    if spec is None:
        raise PublishError(f"no publisher {name!r} (known: {', '.join(publisher_names()) or 'none installed'})")
    module, _, attr = spec.partition(":")
    try:
        cls = getattr(importlib.import_module(module), attr)
    except (ImportError, AttributeError) as e:
        raise PublishError(f"publisher {name!r} ({spec}) could not be loaded: {e}") from None
    if not (isinstance(cls, type) and issubclass(cls, Publisher)):
        raise PublishError(f"publisher {name!r} ({spec}) is not a kb.publish.Publisher subclass")
    return cls


def selected_name(cfg: "kbconfig.KbConfig | None" = None) -> str:
    """The configured publisher name: kb.toml `[publish] publisher`, else `$KB_PUBLISHER`, else "" (none)."""
    cfg = cfg if cfg is not None else kbconfig.current()
    section = cfg.section("publish") if cfg else {}
    name = section.get("publisher")
    if name is None:
        name = os.environ.get(ENV, "")
    return str(name).strip().lower() if str(name).strip().lower() not in NONE_NAMES else ""


def for_kb(cfg: "kbconfig.KbConfig | None" = None, root: Optional[str] = None) -> Publisher:
    """The publisher a kb uses; raises PublishError when the configured one is unknown or cannot load.
    No publisher configured = a `NullPublisher`."""
    cfg = cfg if cfg is not None else kbconfig.current()
    where = root or (cfg.root if cfg else None)
    name = selected_name(cfg)
    if not name:
        return NullPublisher(where)
    options = (cfg.section("publish").get("options") if cfg else None) or {}
    if not isinstance(options, dict):
        raise PublishError("[publish.options] must be a table")
    return load_class(name)(where, **options)


def current(cfg: "kbconfig.KbConfig | None" = None, root: Optional[str] = None) -> Publisher:
    """Like `for_kb`, but never raises: a broken setting gives a `NullPublisher` that says why. Core screens use this."""
    try:
        return for_kb(cfg, root)
    except (PublishError, kbconfig.KbConfigError) as e:
        return NullPublisher(root, reason=str(e))
