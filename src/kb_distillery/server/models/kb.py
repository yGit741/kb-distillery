from typing import Literal

from kb_distillery.server.models.base import ApiModel


class KbGitState(ApiModel):
    repo: bool                      # the folder is its own git repository
    branch: str
    last_tag: str                   # newest kb-x.y.z snapshot tag, "" when none
    dirty: int                      # uncommitted paths (incl. untracked)


class KbType(ApiModel):
    id: str
    label: str
    layer: Literal["source", "collection", "concept"]
    prefix: str
    color: str
    maturities: list[str]


class KbDigestPart(ApiModel):
    part: str                       # focus.md | types.md
    origin: Literal["kb", "explorer"]
    path: str


class KbInfo(ApiModel):
    """The knowledge base this app serves: kb.toml facts, where it is, its types, what it overrides."""
    id: str | None
    name: str
    root: str
    read_only: bool                 # example kb, `[kb] read_only` or $KB_READ_ONLY: no write is accepted
    config: str | None
    schema_version: str
    git: KbGitState
    think_root: str
    think_git: KbGitState
    types: list[KbType]
    areas: list[str]
    source_fields: list[str]
    digest: list[KbDigestPart]
    flags_registry: Literal["explorer", "kb"]
    meta_overrides: list[str]
    bases_dir: str
    relaunch: str


class KbRow(ApiModel):
    id: str
    root: str
    name: str
    schema_version: str
    error: str
    git: KbGitState
    active: bool
    starred: bool                   # pinned to the top of the header menu (<bases dir>/.stars.json)


class KbStarPut(ApiModel):
    starred: bool


class KbList(ApiModel):
    bases_dir: str
    think_root: str
    active: str | None
    kbs: list[KbRow]


class KbGraphSize(ApiModel):
    concepts: int                   # concept-layer nodes
    sources: int                    # source-layer nodes
    edges: int                      # concept-to-concept pairs, one per pair


class KbGraphSizes(ApiModel):
    kbs: dict[str, KbGraphSize]     # by knowledge base id; one that does not load is absent
    pending: list[str] = []         # ids being counted in the background (ask again while this is not empty)
