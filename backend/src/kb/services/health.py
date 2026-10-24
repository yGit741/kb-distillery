"""Vault health snapshot for the API (0 LLM): the lint's metrics without its private row table."""


def build_health_snapshot():
    from kb.lint.lint import collect_snapshot  # lazy: lint imports most of the vault tooling
    snap = collect_snapshot(quiet=True)
    snap.pop("_rows", None)
    return snap
