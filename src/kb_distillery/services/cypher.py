"""Kept only for kb_distillery.graph.propose, which still imports `edge_config` from here (graph/propose.py belongs to
the typed-edges work; its legs stay in pyproject's ignore_imports until that lands). The query service is
kb_distillery.graph.query; everything else imports it, or kb_distillery.graph.model, directly."""
from kb_distillery.graph.model import edge_config  # noqa: F401 — graph/propose.py reads it here

__all__ = ["edge_config"]
