"""A flag's effective value on this machine: a test's forced state, else the owner's runtime override
(`meta/.ops/flags.json`, runtime flags only), else the registry value for the local env.

The pipeline stages read flags here (e.g. `graph.snapshot.relations_on`); `kb_distillery.services.flags` lists and sets
the overrides for the app and gives the same values.
"""
from __future__ import annotations

import json
from pathlib import Path

from kb_distillery.flags.registry import FLAGS_TOML, forced, load
from kb_distillery.paths import OPS_PATH

ENV = "local"                     # the local app and the CLI
OVERRIDES_PATH = Path(OPS_PATH) / "flags.json"


def read_overrides(path: Path | str | None = None) -> dict[str, dict]:
    """{flag: {"value": bool, "at": …}} from the overrides file; {} when it is missing or unreadable."""
    path = Path(path or OVERRIDES_PATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and isinstance(v.get("value"), bool)}


def effective(name: str, env: str = ENV, registry_path=FLAGS_TOML, overrides_path: Path | str | None = None) -> bool:
    """The value of flag `name` right now; an unknown flag or an unreadable registry is off (the safe side)."""
    hit = forced(name)
    if hit is not None:
        return hit
    try:
        flag = next(f for f in load(registry_path).flags if f.name == name)
        o = read_overrides(overrides_path).get(name) if flag.kind == "runtime" else None
        return o["value"] if o else flag.value(env)
    except Exception:                                    # noqa: BLE001 — unreadable registry: the safe side is off
        return False
