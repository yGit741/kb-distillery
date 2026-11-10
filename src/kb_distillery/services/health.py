"""Vault health snapshot for the API (0 LLM): the lint's metrics without its private row table.

The full lint pass takes seconds on a large kb, so the result is reused while the vault's change signature
(`graph.cache.full_signature`: wiki, raw, meta, root files, git HEAD) is the same; any edit rebuilds."""
import copy


def _build():
    from kb_distillery.lint.lint import collect_snapshot  # lazy: lint imports most of the vault tooling
    snap = collect_snapshot(quiet=True)
    snap.pop("_rows", None)
    return snap


def build_health_snapshot():
    from kb_distillery.graph import cache, snapshot
    root = snapshot.ROOT
    return copy.deepcopy(cache.memo("health:" + root, lambda: cache.full_signature(root), _build))
