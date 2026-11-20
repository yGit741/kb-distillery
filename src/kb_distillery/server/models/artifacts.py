"""GET /api/artifacts — mirrors kb_distillery.services.artifacts.load(): a kb's `artifacts/graph.json` plus `cites`.

The file is written by a builder (a code toolkit's `export`, say), not by the engine, so every model keeps
`extra="allow"`: a builder may add fields the graph does not read yet.
"""
from typing import Literal

from kb_distillery.server.models.base import ApiModel


class ArtifactNode(ApiModel):
    id: str
    type: str
    name: str
    parent: str | None = None          # the containment tree (a folder's file, a file's class); roots are repositories
    repo: str | None = None
    path: str | None = None
    line: int | None = None
    url: str | None = None             # a repository's own page at its source host
    stage: str | None = None           # a model: the class that loads it
    commits: int | None = None


class ArtifactLink(ApiModel):
    source: str
    target: str
    kind: str
    weight: float | None = None
    at: str | None = None              # `<repo>:<path>#L<line>`: where the code says so


class ArtifactView(ApiModel):
    """A view the builder declares: which types and relations it draws."""
    id: str
    name: str
    hint: str | None = None
    builder: str | None = None
    types: list[str]
    relations: list[str] | None = None
    color_by: str | None = None        # repo | stage | type
    size_by: str | None = None
    nest: Literal["tree", "none"] | None = None   # tree (default): drill down the containment tree; none: all at once


class ArtifactCard(ApiModel):
    """A fact card: fact id (`F` + 5 hex digits) -> the artifact nodes it is about."""
    title: str | None = None
    repo: str | None = None
    nodes: list[str] | None = None
    facts: dict[str, list[str]] | None = None


class ArtifactRepo(ApiModel):
    sha: str | None = None
    web: str | None = None             # the repository's web address; permalinks are built from it and `sha`


class ArtifactType(ApiModel):
    description: str | None = None
    mark: str | None = None            # repo | ring | dot, or a built-in mark name


class ArtifactRelation(ApiModel):
    description: str | None = None
    directed: bool | None = None


class ArtifactGraph(ApiModel):
    version: int | None = None
    template: str | None = None
    project: str | None = None
    generator: str | None = None       # the tool that wrote the graph
    nodes: list[ArtifactNode]
    links: list[ArtifactLink]
    repos: dict[str, ArtifactRepo] | None = None
    cards: dict[str, ArtifactCard] | None = None
    types: dict[str, ArtifactType] | None = None
    relations: dict[str, ArtifactRelation] | None = None
    views: list[ArtifactView] | None = None
    cites: dict[str, list[str]] = {}   # page slug -> the fact ids its text cites, in order of first mention
