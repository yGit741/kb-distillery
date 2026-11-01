"""The per-user config folder: `~/.config/kb-distillery/` (API key, chat settings and keys, usage ledger, engine.toml).

One place knows the folder, so nothing else spells the path. It used to be `~/.config/thesis-kb/`; the engine never
moves a user's files on its own: when only the old folder exists, `check()` says so with the exact `mv` and the CLI
exits 1 (`distill doctor` reports it as a failing check). Imports nothing from `kb_distillery`: `distill --help` and the
hooks must work with no knowledge base selected.

Paths are computed from `$HOME` at call time (`config_dir()`); modules that keep a constant (`llm.KEY_FILE`) take it at
import, and tests point `HOME` at a temp folder (or patch the constant) so they never read the real one.
"""
from __future__ import annotations

import os
import shlex

APP_DIR = "kb-distillery"
LEGACY_APP_DIR = "thesis-kb"
# macOS keychain service names (the login keychain is the user's, so it is never renamed for them): a lookup tries the
# new name, then the old one it replaces; adding an item always uses the new name.
KEYCHAIN_LEGACY = {"kb-distillery-gmail": "thesis-kb-gmail", "kb-distillery-gmail-imap": "thesis-kb-gmail-imap"}


def keychain_services(service: str) -> list[str]:
    """The keychain service names to try for `service`, newest first."""
    old = KEYCHAIN_LEGACY.get(service)
    return [service, old] if old else [service]


def _dot_config() -> str:
    return os.path.join(os.path.expanduser("~"), ".config")


def config_dir() -> str:
    """`~/.config/kb-distillery` (not created here)."""
    return os.path.join(_dot_config(), APP_DIR)


def legacy_dir() -> str:
    """`~/.config/thesis-kb`, the folder this one replaces."""
    return os.path.join(_dot_config(), LEGACY_APP_DIR)


def path(*parts: str) -> str:
    """A file or folder inside the config folder, e.g. `path("anthropic_key")`, `path("keys", "s2")`."""
    return os.path.join(config_dir(), *parts)


def display(*parts: str) -> str:
    """`path(...)` written with `~`, for messages the user reads."""
    home = os.path.expanduser("~")
    p = path(*parts)
    return "~" + p[len(home):] if p.startswith(home + os.sep) else p


def migration_needed() -> bool:
    """True when only the old folder exists (the new one does not)."""
    return os.path.isdir(legacy_dir()) and not os.path.exists(config_dir())


def migration_command() -> str:
    return f"mv {shlex.quote(legacy_dir())} {shlex.quote(config_dir())}"


def migration_message() -> str:
    return (f"kb-distillery keeps its per-user files in {display()} now; only the old folder {legacy_dir()} exists.\n"
            f"Nothing is moved for you. Move it yourself, then run this command again:\n  {migration_command()}")


def check() -> str | None:
    """The migration message when the user has to move the old folder first, else None."""
    return migration_message() if migration_needed() else None
