"""One rule for the routes that spend a model call or open a chat: a read-only server (KB_READ_ONLY=1, a hosted or share-like
deployment) answers them with 405, the way the views, favorites and sessions routers refuse their writes."""
import os

from fastapi import HTTPException

READ_ONLY_ENV = "KB_READ_ONLY"


def is_read_only() -> bool:
    return os.environ.get(READ_ONLY_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def refuse_when_read_only() -> None:
    """A FastAPI dependency: `dependencies=[Depends(refuse_when_read_only)]` on a route that must not run on a read-only server."""
    if is_read_only():
        raise HTTPException(status_code=405, detail=f"this server is read-only ({READ_ONLY_ENV} is set): this action is not available here")
