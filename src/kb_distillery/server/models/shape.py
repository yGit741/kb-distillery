"""Models of POST /api/graph/shape — free text to a Cypher selection plus a style clause (kb_distillery.graph.shape)."""
from typing import Literal

from pydantic import Field

from kb_distillery.graph.shape import StyleSpec
from kb_distillery.server.models.base import ApiModel
from kb_distillery.server.models.cypher import QueryTable


class ShapeRequest(ApiModel):
    text: str = Field(..., max_length=4000, description="Free text, raw Cypher (starts with MATCH, style after a "
                      "`--` or `style:` line), or a style clause list on its own")
    limit: int = Field(500, ge=1, le=500)
    backend: Literal["subscription", "api", "batch"] | None = Field(
        None, description="LLM backend for this request; default $KB_LLM_BACKEND, then subscription")


class ShapeResponse(QueryTable):
    cypher: str | None = Field(None, description="null when the text was a style clause only: keep the current nodes")
    style: StyleSpec
    style_text: str = Field("", description="the style in its canonical clause form")
    explanation: str = ""
    source: Literal["cypher", "llm"] = Field(..., description="`llm` when the model wrote the Cypher")
    warnings: list[str] = []
    backend: str | None = Field(None, description="the LLM backend that answered; null without an LLM call")
    usd: float | None = Field(None, description="cost reported by the backend; null without an LLM call")
