"""The layer objects (a view is an ordered stack of them), as pydantic models.

They mirror `web/src/features/graph/layers/model.ts` field for field (that file is the contract): the same
names, the same discriminator key `t` on every condition, the same optional fields. A change to one needs the other, and
`tests/fixtures/layers/*.json` is checked on both sides (pytest in tests/server/test_layers.py, vitest in
`layers/parity.test.ts`). They live in the graph package, like StyleSpec, so the translator can validate a model answer
without importing the server; `kb_distillery.server.models.layers` re-exports them.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

Op = Literal[">=", ">", "<=", "<", "="]
ColorBy = Literal["type", "layer", "depth", "status", "area", "degree", "evidence", "score", "none", "format", "recency", "added", "support"]
SizeBy = Literal["connections", "in", "out", "uniform", "tier", "evidence", "score", "gap", "logdeg"]
Width = Literal["thin", "normal", "thick"]


class Strict(BaseModel):
    """A layer object is exactly what the frontend model allows: an unknown key is an error, not a guess."""
    model_config = ConfigDict(extra="forbid")


# ---- conditions on pages (NodeCond)
class TypeCond(Strict):
    t: Literal["type"]
    value: str | list[str]


class DegreeCond(Strict):
    t: Literal["degree"]
    op: Op
    n: int


class HopsCond(Strict):
    t: Literal["hops"]
    of: str = Field(..., description="a page slug or title, `$favorites` or `$focus`")
    n: int


class NameCond(Strict):
    t: Literal["name"]
    slugs: list[str]


class TextCond(Strict):
    t: Literal["text"]
    phrase: str


class FavoriteCond(Strict):
    t: Literal["favorite"]


class AboutCond(Strict):
    t: Literal["about"]
    phrase: str


class InAreaCond(Strict):
    t: Literal["inArea"]
    area: str


class CreatedWithinCond(Strict):
    t: Literal["createdWithin"]
    days: int


class LinkedFromTypeCond(Strict):
    t: Literal["linkedFromType"]
    type: str


class PathsCond(Strict):
    t: Literal["paths"]
    a: str
    b: str
    n: int


class HasEdgeCond(Strict):
    t: Literal["hasEdge"]
    type: str
    exists: Literal[False] | None = None


class MentionedInCond(Strict):
    t: Literal["mentionedIn"]
    chat: str


class AllNodesCond(Strict):
    t: Literal["all"]


class NotCond(Strict):
    t: Literal["not"]
    cond: "NodeCond"


NodeCond = Annotated[
    Union[TypeCond, DegreeCond, HopsCond, NameCond, TextCond, FavoriteCond, AboutCond, InAreaCond, CreatedWithinCond,
          LinkedFromTypeCond, PathsCond, HasEdgeCond, MentionedInCond, NotCond, AllNodesCond],
    Field(discriminator="t")]
NotCond.model_rebuild()


# ---- conditions on links (EdgeCond)
class EdgeTypeCond(Strict):
    t: Literal["type"]
    value: str


class DirectionCond(Strict):
    t: Literal["direction"]
    value: Literal["in", "out", "both"]


class EndpointsCond(Strict):
    t: Literal["endpoints"]
    slugs: list[str]


class CountCond(Strict):
    t: Literal["count"]
    op: Op
    n: int


class AllEdgesCond(Strict):
    t: Literal["all"]


EdgeCond = Annotated[Union[EdgeTypeCond, DirectionCond, EndpointsCond, CountCond, AllEdgesCond],
                     Field(discriminator="t")]


class By(Strict):
    by: str = Field(..., description="a page property or `degree`")


class Subgraph(Strict):
    nodes: list[NodeCond] | None = None
    edges: list[EdgeCond] | None = None


class LayerStyle(Strict):
    color: ColorBy | By | None = None
    size: SizeBy | By | None = None
    width: Width | By | None = None
    label: str | None = None


class Layer(Strict):
    id: str
    kind: Literal["show", "hide", "style"]
    target: Literal["nodes", "edges"]
    subgraph: Subgraph
    style: LayerStyle | None = None
    text: str = Field(..., description="plain words for the chip; empty lets the app describe the layer")


class ViewStack(Strict):
    v: Literal[2]
    layers: list[Layer]
