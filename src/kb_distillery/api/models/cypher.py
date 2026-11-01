"""Models of POST /api/graph/cypher and /api/graph/queries — read-only graph queries (kb_distillery.services.cypher)."""
from typing import Any

from pydantic import Field

from kb_distillery.api.models.base import ApiModel


class CypherRequest(ApiModel):
    query: str = Field(..., max_length=4000, description="Cypher (supported subset); strings in double quotes")
    limit: int = Field(500, ge=1, le=500)


class NamedQueryRequest(ApiModel):
    params: dict[str, str] = {}
    limit: int = Field(500, ge=1, le=500)


class QueryTable(ApiModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool = False


class NamedQuery(ApiModel):
    name: str
    description: str
    params: list[str] = []
