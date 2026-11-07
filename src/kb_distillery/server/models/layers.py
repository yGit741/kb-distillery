"""Models of POST /api/graph/layers. The layer objects themselves are in `kb_distillery.graph.layers` (they mirror
`web/src/features/graph/layers/model.ts`) and are re-exported here for the typed client."""
from typing import Literal

from pydantic import Field

from kb_distillery.graph.layers import EdgeCond, Layer, LayerStyle, NodeCond, Subgraph, ViewStack  # noqa: F401
from kb_distillery.server.models.base import ApiModel

# ---- the endpoint
class LayersRequest(ApiModel):
    text: str = Field(..., max_length=4000, description="A `>` sentence the rules parser could not read")
    op: Literal["replace", "stack", "remove"] = Field(
        "replace", description="How the caller will combine the answer with the current view; `remove` asks which "
        "layer the text names")
    backend: Literal["subscription", "api", "batch"] | None = Field(
        None, description="LLM backend for this request; default $KB_LLM_BACKEND, then subscription. `batch` waits "
        "minutes to hours and does not suit an interactive line")
    fallback: Literal["subscription", "api", "batch", "none"] | None = Field(
        None, description="Backend tried once when the first one is unavailable, fails or is rate-limited. Default: "
        "`api` when the first is the subscription (and a key exists), else none. `none` turns it off")


class LayersResponse(ApiModel):
    layers: list[Layer]
    lines: list[str] = Field(..., description="each layer in the query language, one line per layer")
    explanation: str = ""
    backend: str = Field(..., description="the LLM backend that answered")
    fallback_from: str | None = Field(None, description="the backend tried first, when `backend` took over from it")
    usd: float = Field(0.0, description="cost reported by the backend that answered")
    warnings: list[str] = []
