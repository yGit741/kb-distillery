"""Feature-flag registry: `meta/flags.toml` -> validated `Registry`.

One `[[flag]]` table per flag (name, description, owner, created, expires, kind, default, envs). `load()`
raises `FlagError` listing every problem by flag name; `value(name, env)` is the build-time value — runtime
overrides (G2) will layer on top of it for `kind = "runtime"` flags only.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from kb_distillery.paths import META_DEFAULTS_PATH, ROOT, meta_file

# The explorer's `src/kb_distillery/kits/base/defaults/flags.toml`, unless the knowledge base carries its own `meta/flags.toml`.
FLAGS_TOML = Path(meta_file("flags.toml"))
FLAGS_SOURCE = "kb" if not str(FLAGS_TOML).startswith(META_DEFAULTS_PATH) else "explorer"
ENVS = ("local", "private", "public")
Env = Literal["local", "private", "public"]
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*$")


# Test seam: `override()` (used by the pytest `flag` marker, tests/conftest.py) forces a value for
# every env. Never set outside tests.
_OVERRIDES: dict[str, bool] = {}


@contextlib.contextmanager
def override(name: str, on: bool):
    """Force flag `name` to `on` in every env for the duration (tests only)."""
    had, old = name in _OVERRIDES, _OVERRIDES.get(name)
    _OVERRIDES[name] = bool(on)
    try:
        yield
    finally:
        if had:
            _OVERRIDES[name] = old
        else:
            _OVERRIDES.pop(name, None)


def forced(name: str) -> bool | None:
    """The state a test forced with `override`, or None."""
    return _OVERRIDES.get(name)


class FlagError(ValueError):
    """meta/flags.toml is missing, unreadable or invalid; the message lists every problem."""


class Envs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    local: bool
    private: bool
    public: bool


class Flag(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    name: str
    description: str
    owner: str
    created: dt.date
    expires: dt.date
    kind: Literal["runtime", "build"]
    default: bool
    envs: Envs

    @model_validator(mode="after")
    def _check(self):
        if not NAME_RE.match(self.name):
            raise ValueError(f"name {self.name!r} must be dotted lower-case words, e.g. screen.lifecycle")
        if not self.description.strip() or not self.owner.strip():
            raise ValueError("description and owner must not be empty")
        if self.expires <= self.created:
            raise ValueError(f"expires {self.expires} must be after created {self.created}")
        return self

    def value(self, env: str) -> bool:
        if self.name in _OVERRIDES:
            return _OVERRIDES[self.name]
        return getattr(self.envs, env) if env in ENVS else self.default


class Registry(BaseModel):
    flags: tuple[Flag, ...]

    def names(self) -> list[str]:
        return [f.name for f in self.flags]

    def get(self, name: str) -> Flag:
        for f in self.flags:
            if f.name == name:
                return f
        raise KeyError(f"unknown flag {name!r} (known: {', '.join(self.names()) or 'none'})")

    def value(self, name: str, env: str) -> bool:
        return self.get(name).value(env)


def _where(loc) -> str:
    return ".".join(str(p) for p in loc) or "(flag)"


def parse(data: dict, source: str = "flags.toml") -> Registry:
    """Validate parsed TOML; collect every error before raising."""
    extra = set(data) - {"flag"}
    errors = [f"unknown top-level key(s) {sorted(extra)}; use [[flag]] tables"] if extra else []
    flags, seen = [], set()
    for i, raw in enumerate(data.get("flag", [])):
        label = raw.get("name") if isinstance(raw, dict) and isinstance(raw.get("name"), str) else f"#{i + 1}"
        try:
            f = Flag.model_validate(raw)
        except ValidationError as e:
            for err in e.errors():
                errors.append(f"flag {label}: {_where(err['loc'])}: {err['msg']}")
            continue
        if f.name in seen:
            errors.append(f"flag {f.name}: duplicate name")
        seen.add(f.name)
        flags.append(f)
    if errors:
        raise FlagError(f"{source} is invalid:\n  " + "\n  ".join(errors))
    return Registry(flags=tuple(sorted(flags, key=lambda f: f.name)))


def load(path: Path | str = FLAGS_TOML) -> Registry:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FlagError(f"{path} not found") from None
    except tomllib.TOMLDecodeError as e:
        raise FlagError(f"{path}: TOML syntax error: {e}") from None
    return parse(data, str(path))


def value(name: str, env: str, path: Path | str = FLAGS_TOML) -> bool:
    """Build-time value of flag `name` in `env` (local | private | public; unknown env -> default)."""
    return load(path).value(name, env)
