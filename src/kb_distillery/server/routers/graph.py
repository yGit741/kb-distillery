"""GET /api/graph — the wiki link graph; `?layer=raw` merges the private data layer in; `?kb=a,b` shows other
knowledge bases (read-only), several on one canvas with ids `<kb>:<slug>`."""
from fastapi import APIRouter, HTTPException, Query

from kb_distillery.server.models.graph import GraphSnapshot
from kb_distillery.services import kbview
from kb_distillery.graph.cache import cached_graph_snapshot
from kb_distillery.graph.snapshot import merge_snapshots

router = APIRouter(tags=["graph"])


@router.get("/api/graph", response_model=GraphSnapshot, summary="Wiki link graph",
            responses={400: {"description": "raw layer of another knowledge base"},
                       404: {"description": "unknown knowledge base"}})
def get_graph(layer: str = Query("", description="`raw` adds the data layer; anything else is ignored"),
              kb: str = Query("", description="comma-separated knowledge base ids; empty = the server's own")):
    raw = "raw" if layer == "raw" else None
    ids = list(dict.fromkeys(k.strip() for k in kb.split(",") if k.strip()))
    try:
        views = [kbview.view(i) for i in ids] or [kbview.active_view()]
    except KeyError as e:
        raise HTTPException(404, f"unknown knowledge base {e.args[0]!r}") from None
    if raw and not all(v.active for v in views):
        raise HTTPException(400, "the raw layer is only available for the server's own knowledge base")
    if len(views) == 1:
        v = views[0]
        snap = cached_graph_snapshot(layer=raw, view=None if v.active else v)
        snap["kbs"] = [{"id": v.id, "name": v.name, "active": v.active}]
        return snap
    return merge_snapshots([(v, cached_graph_snapshot(view=None if v.active else v)) for v in views])
