"""Typed feature-flag registry (meta/flags.toml) shared by backend and frontend."""
from kb.flags.registry import ENVS, Flag, FlagError, Registry, load, value

__all__ = ["ENVS", "Flag", "FlagError", "Registry", "load", "value"]
